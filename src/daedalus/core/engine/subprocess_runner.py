"""Run one module in a child interpreter and read its manifest back.

The uv and nix isolation strategies (``isolation.py``) launch every isolated
step through this module; ``dae lab validate --deep`` probes imports through it.
The child runs the PEP 723 shim ``_module_runner.py`` with the module dir and a
JSON FlowContext, then writes ``dae-manifest.json``. A nonzero rc reads as
``failed``, a missing manifest raises :class:`SubprocessStepError`, and a
missing third-party package arrives on stderr as ``DAE_MISSING_PACKAGE=``.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from daedalus import __version__ as _VERSION
from daedalus.core import lineage

if TYPE_CHECKING:
    from collections.abc import Sequence

    import daedalus.flow as dae

# The PEP 723 shim run in the child; a sibling module, so it ships in the wheel.
_DEFAULT_SHIM = Path(__file__).resolve().parent / "_module_runner.py"
# Three parents up from core/engine/subprocess_runner.py is the package dir in
# every layout; one more step lands on the checkout root in a src layout but on
# <venv>/lib/pythonX.Y once installed (see _daedalus_import_root).
_PACKAGE_DIR = Path(__file__).resolve().parents[2]
# The package name a child must import, and the only name an import root exposes.
_PACKAGE_NAME = _PACKAGE_DIR.name
# The import-only probe shim, launched by probe_import for `dae lab validate
# --deep`; it loads a module's main.py but never calls the entry.
_DEFAULT_PROBE = Path(__file__).resolve().parent / "_import_probe.py"

# The stderr marker the child writes for a missing dependency. It mirrors
# _module_runner.MISSING_PACKAGE_MARKER so the parent needs no child-script import.
_MISSING_PACKAGE_MARKER = "DAE_MISSING_PACKAGE="

# Hex chars kept from the import-root digest, as for the flake dirs in
# isolation.py; 16 hex chars is 64 bits, enough to keep two installs apart.
_ROOT_DIGEST_HEXLEN = 16


def _exposes_only_daedalus(candidate: Path) -> bool:
    """True when *candidate* exposes ``daedalus`` and nothing else importable."""
    # A src-layout src/ qualifies; site-packages does not. Unknown entries
    # disqualify, so an odd layout stages a clean root instead of leaking one;
    # an empty dir fails because the package itself must be present.
    try:
        entries = list(candidate.iterdir())
    except OSError:
        return False
    return (candidate / _PACKAGE_NAME).is_dir() and all(
        entry.name in (_PACKAGE_NAME, "__pycache__") for entry in entries
    )


def _content_signature(package_dir: Path) -> str:
    """Path, size and mtime per file, so a reinstall at the same version changes it."""
    # Stat metadata rather than content hashing; a few hundred stats per launch.
    digest = hashlib.sha256()
    for path in sorted(package_dir.rglob("*")):
        if "__pycache__" in path.parts or not path.is_file():
            continue
        stat = path.stat()
        digest.update(
            f"{path.relative_to(package_dir)}\x00{stat.st_size}"
            f"\x00{stat.st_mtime_ns}\n".encode()
        )
    return digest.hexdigest()


def _staged_import_root(package_dir: Path) -> Path:
    """A cached directory under the user cache that exposes only ``daedalus``."""
    # Keyed by package path, version and content signature, so two venvs never
    # share a root and a changed install lands in a fresh entry.
    # TODO: prune superseded keyed dirs; each reinstall leaves one small dir.
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(
        os.path.expanduser("~"), ".cache"
    )
    key = hashlib.sha256(
        f"{package_dir}\n{_VERSION}\n{_content_signature(package_dir)}".encode()
    ).hexdigest()
    home = Path(base) / "daedalus" / "import-roots" / key[:_ROOT_DIGEST_HEXLEN]
    root = home / "root"
    entry = root / _PACKAGE_NAME
    try:
        # exists() follows the symlink, so a live published entry (link target
        # still present, or a completed copy) is reused as-is.
        if entry.exists():
            return root
        # A dangling entry (the install moved) cannot be repaired in place; drop
        # the keyed dir and re-stage. Racing processes re-stage equivalent
        # content, and ignore_errors covers the one whose rmtree loses.
        if home.exists():
            shutil.rmtree(home, ignore_errors=True)
        # mkdtemp, not a pid-suffixed name: racing resolvers can be threads of
        # one process (a scheduler wave), so the staging dir must be unique per
        # attempt, not per process.
        home.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(
            tempfile.mkdtemp(prefix=f".staging-{home.name}-", dir=home.parent)
        )
        try:
            (staging / "root").mkdir()
            staged_entry = staging / "root" / _PACKAGE_NAME
            try:
                staged_entry.symlink_to(package_dir, target_is_directory=True)
            except OSError:
                # A platform or filesystem that refuses symlinks. The package is
                # small and pure-Python, so a copy is cheap; the content-keyed
                # dir name re-materialises it on any change to the install.
                shutil.copytree(package_dir, staged_entry)
            try:
                os.replace(staging, home)
            except OSError:
                # Another resolver published the same key first and its entry is
                # equivalent, so this staging copy is dropped. Any other failure
                # re-raises into the SubprocessStepError below.
                if not entry.exists():
                    raise
        finally:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
    except OSError as error:
        raise SubprocessStepError(
            f"cannot stage the child import root under {home}: {error}; "
            "set `XDG_CACHE_HOME` to a writable directory"
        ) from error
    return root


def _daedalus_import_root() -> Path:
    """The package's parent when it exposes only ``daedalus``, else a staged root."""
    parent = _PACKAGE_DIR.parent
    if _exposes_only_daedalus(parent):
        return parent
    return _staged_import_root(_PACKAGE_DIR)


class SubprocessStepError(Exception):
    """The child left no readable manifest, or the import root cannot be staged."""


@dataclass(frozen=True)
class SubprocessStepResult:
    """The outcome of running one module in a child interpreter."""

    status: str  # the terminal manifest status, completed or failed
    returncode: int
    missing_package: str | None  # top-level package the child found missing
    error: str | None
    stderr: str  # the merged step.log text


def _context_to_json(ctx: dae.FlowContext) -> dict[str, object]:
    """Serialize a FlowContext to the JSON the child reconstructs."""
    return {
        "step_id": ctx.step_id,
        "role": str(ctx.role),
        "step_input_path": str(ctx.step_input_path),
        "step_output_path": str(ctx.step_output_path),
        "flight_id": ctx.flight_id,
        "walk_id": ctx.walk_id,
        "walk_inputs": {k: str(v) for k, v in ctx.walk_inputs.items()},
        "flight_inputs": {k: str(v) for k, v in ctx.flight_inputs.items()},
        "seed": ctx.seed,
    }


def _child_env(import_root: Path) -> dict[str, str]:
    """Scrubbed env for the uv child, with ``PYTHONPATH`` re-added after the scrub."""
    env = _clean_subprocess_env()
    env["PYTHONPATH"] = str(import_root)
    # Without safe path the child prepends the shim's dir (core/engine) to
    # sys.path ahead of the import root, exposing engine internals as top-level
    # modules; the shims use absolute daedalus.* imports and need nothing there.
    env["PYTHONSAFEPATH"] = "1"
    return env


# Variables that let a host interpreter, venv, conda env, uv project or loader
# path shadow the child's own environment. `UV_PYTHON` would override the child's
# `UV_MANAGED_PYTHON=1` and launch the host python instead of the standalone one.
_POLLUTION_VARS = (
    "LD_LIBRARY_PATH",
    "LD_PRELOAD",
    "PYTHONPATH",
    "PYTHONHOME",
    "VIRTUAL_ENV",
    "UV_PYTHON",
)

_POLLUTION_PREFIXES = ("CONDA_", "UV_PROJECT")


def _clean_subprocess_env() -> dict[str, str]:
    """The parent env minus the pollution set, plus ``UV_MANAGED_PYTHON=1``."""
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in _POLLUTION_VARS and not key.startswith(_POLLUTION_PREFIXES)
    }
    env["UV_MANAGED_PYTHON"] = "1"
    return env


def _uv_run_prefix(*, requirements: Sequence[str]) -> list[str]:
    """The ``uv run`` prefix shared by the run line and the import probe."""
    # --managed-python picks a uv standalone interpreter, which loads manylinux
    # wheels without an LD_LIBRARY_PATH shim; --no-config and --no-project keep
    # any ambient uv.toml, pyproject.toml and uv.lock out of the resolution.
    cmd = [
        "uv",
        "run",
        "--managed-python",
        "--no-config",
        "--no-project",
    ]
    # daedalus itself is not installed into the child; the shims are stdlib-only
    # and reach it over PYTHONPATH (see _child_env).
    for req in requirements:
        cmd += ["--with", req]
    return cmd


def _build_command(
    *,
    shim_path: Path,
    requirements: Sequence[str],
    module_dir: Path,
    ctx_json_path: Path,
) -> list[str]:
    """The ``uv run --script`` launch line for the child."""
    cmd = _uv_run_prefix(requirements=requirements)
    cmd += ["--script", str(shim_path), str(module_dir), str(ctx_json_path)]
    return cmd


def _parse_missing_package(stderr: str) -> str | None:
    """Extract the out-of-band missing-package name from the child stderr, if any."""
    for line in stderr.splitlines():
        if line.startswith(_MISSING_PACKAGE_MARKER):
            name = line[len(_MISSING_PACKAGE_MARKER) :].strip()
            if name:
                return name
    return None


def _module_requirements(module_dir: Path) -> list[str]:
    """Specs from the module's requirements.txt, one per line; ``[]`` when absent."""
    # TODO: switch to `uv run --with-requirements` if markers or -r includes appear.
    req_file = module_dir / "requirements.txt"
    if not req_file.is_file():
        return []
    specs: list[str] = []
    for raw in req_file.read_text().splitlines():
        # Strip an inline comment (pip requires whitespace before the '#').
        line = raw.split(" #", 1)[0].split("\t#", 1)[0].strip()
        if not line or line.startswith("#"):
            continue
        specs.append(line)
    return specs


def run_step_subprocess(
    module_dir: Path,
    ctx: dae.FlowContext,
    *,
    import_root: Path | None = None,
    requirements: Sequence[str] = (),
    shim_path: Path | None = None,
) -> SubprocessStepResult:
    """Run ``module_dir`` in a child interpreter and read its manifest back.

    Writes the FlowContext as JSON in the step dir and launches the shim with
    ``uv run --script``. A nonzero rc reads as ``failed``, a missing manifest raises
    :class:`SubprocessStepError`, a missing dependency sets ``missing_package``.
    """
    module_dir = Path(module_dir)
    import_root = (
        Path(import_root) if import_root is not None else _daedalus_import_root()
    )
    shim_path = Path(shim_path) if shim_path is not None else _DEFAULT_SHIM
    step_dir = Path(ctx.step_output_path)
    step_dir.mkdir(parents=True, exist_ok=True)

    ctx_json_path = step_dir / "dae-context.json"
    ctx_json_path.write_text(json.dumps(_context_to_json(ctx), indent=2))

    # The engine's uv strategy passes no requirements, so the module's own
    # requirements.txt provisions the child.
    effective_requirements = (
        requirements if requirements else _module_requirements(module_dir)
    )
    command = _build_command(
        shim_path=shim_path,
        requirements=effective_requirements,
        module_dir=module_dir,
        ctx_json_path=ctx_json_path,
    )
    return _run_child(command, step_dir=step_dir, env=_child_env(import_root))


def _run_child(
    command: list[str], *, step_dir: Path, env: dict[str, str]
) -> SubprocessStepResult:
    """Run a launcher argv with output in ``step.log`` and read the manifest back."""
    # stdout and stderr stream into step.log as the child runs, so a user can
    # tail it and the log travels with the step dir.
    log_path = step_dir / "step.log"
    with log_path.open("w") as log:
        completed = subprocess.run(  # noqa: S603 (fixed argv, no shell)
            command,
            stdout=log,
            stderr=subprocess.STDOUT,
            env=env,
            check=False,
        )
    returncode = completed.returncode
    # The log is written as bytes, so decode it here; errors="replace" keeps a
    # stray non-utf-8 byte from masking the real outcome.
    output = log_path.read_text(encoding="utf-8", errors="replace")
    missing_package = _parse_missing_package(output)

    try:
        manifest = lineage.read_step_manifest(step_dir)
    except lineage.LineageError as error:
        # The child left no readable manifest and its outcome cannot be resolved;
        # raise instead of fabricating a status.
        raise SubprocessStepError(
            f"child wrote no readable dae-manifest.json in {step_dir} "
            f"(rc={returncode}): {error}; step.log:\n{output}"
        ) from error

    # A nonzero rc reads as failed even when the manifest says completed.
    status = "failed" if returncode != 0 else manifest.status

    return SubprocessStepResult(
        status=status,
        returncode=returncode,
        missing_package=missing_package,
        error=manifest.error,
        stderr=output,
    )


def read_step_log_tail(step_dir: Path, max_lines: int = 20) -> str:
    """The last ``max_lines`` lines of a step's ``step.log``, or ``""`` when absent.

    The log holds the child's merged stdout and stderr, so the tail shows a
    traceback or the last sampling line without re-running anything.
    """
    log_path = Path(step_dir) / "step.log"
    if not log_path.is_file():
        return ""
    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(lines[-max_lines:])


def _nix_shell_prefix(*, flake_ref: str, env_attr: str) -> list[str]:
    """The ``nix shell`` prefix shared by the run line and the import probe."""
    # The experimental-features flag makes the line work on a host whose
    # nix.conf does not enable flakes.
    return [
        "nix",
        "shell",
        "--extra-experimental-features",
        "nix-command flakes",
        f"{flake_ref}#{env_attr}",
        "--command",
        "python",
    ]


def _build_nix_command(
    *,
    flake_ref: str,
    env_attr: str,
    shim_path: Path,
    module_dir: Path,
    ctx_json_path: Path,
) -> list[str]:
    """The ``nix shell`` launch line for the child; the shim contract matches uv."""
    return [
        *_nix_shell_prefix(flake_ref=flake_ref, env_attr=env_attr),
        str(shim_path),
        str(module_dir),
        str(ctx_json_path),
    ]


def _nix_child_env(import_root: Path) -> dict[str, str]:
    """The shared scrub narrowed to what ``nix`` needs, plus ``PYTHONPATH``."""
    # The closure carries its own system libs, so a nix child sees only what
    # nix needs to evaluate and substitute, plus the daedalus import root.
    keep = (
        "HOME",
        "USER",
        "PATH",
        "TERM",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "TZ",
        "NIX_PATH",
        "NIX_REMOTE",
        "NIX_SSL_CERT_FILE",
        "SSL_CERT_FILE",
        "XDG_CACHE_HOME",
        "XDG_CONFIG_HOME",
        "XDG_DATA_HOME",
        "XDG_RUNTIME_DIR",
    )
    scrubbed = _clean_subprocess_env()
    env = {k: scrubbed[k] for k in keep if k in scrubbed}
    env["PYTHONPATH"] = str(import_root)
    # Keep the shim's own directory off sys.path, as in _child_env.
    env["PYTHONSAFEPATH"] = "1"
    # `DAE_ISOLATION=nix` marks the nix strategy; uv and ambient children never
    # set it.
    env["DAE_ISOLATION"] = "nix"
    return env


def run_step_nix(
    module_dir: Path,
    ctx: dae.FlowContext,
    *,
    flake_ref: str,
    env_attr: str = "default",
    import_root: Path | None = None,
    shim_path: Path | None = None,
) -> SubprocessStepResult:
    """Run ``module_dir`` under its per-module nix env and read the manifest back.

    The nix sibling of :func:`run_step_subprocess`, with the same JSON sidecar and
    manifest, launched with ``nix shell <flake_ref>#<env_attr>`` (the env built by
    :meth:`NixStrategy.provision`) under :func:`_nix_child_env`.
    """
    module_dir = Path(module_dir)
    import_root = (
        Path(import_root) if import_root is not None else _daedalus_import_root()
    )
    shim_path = Path(shim_path) if shim_path is not None else _DEFAULT_SHIM
    step_dir = Path(ctx.step_output_path)
    step_dir.mkdir(parents=True, exist_ok=True)

    ctx_json_path = step_dir / "dae-context.json"
    ctx_json_path.write_text(json.dumps(_context_to_json(ctx), indent=2))

    command = _build_nix_command(
        flake_ref=flake_ref,
        env_attr=env_attr,
        shim_path=shim_path,
        module_dir=module_dir,
        ctx_json_path=ctx_json_path,
    )
    return _run_child(command, step_dir=step_dir, env=_nix_child_env(import_root))


def probe_import(
    module_dir: Path,
    *,
    strategy_name: str,
    flake_ref: str | None = None,
    import_root: Path | None = None,
    probe_path: Path | None = None,
) -> SubprocessStepResult:
    """Import a module's entry under its resolved env without calling it.

    Launches :data:`_DEFAULT_PROBE` with the launcher and scrubbed env a run would
    use, uv or nix. A nonzero rc reads as ``failed`` and a missing package sets
    ``missing_package``; the probe writes no manifest, so rc and stderr are the result.
    """
    module_dir = Path(module_dir)
    import_root = (
        Path(import_root) if import_root is not None else _daedalus_import_root()
    )
    probe_path = Path(probe_path) if probe_path is not None else _DEFAULT_PROBE

    if strategy_name == "nix":
        if flake_ref is None:
            msg = "probe_import(strategy_name='nix') requires a flake_ref"
            raise ValueError(msg)
        # Mirrors _build_nix_command minus the ctx arg (the probe takes none).
        command = [
            *_nix_shell_prefix(flake_ref=flake_ref, env_attr="default"),
            str(probe_path),
            str(module_dir),
        ]
        env = _nix_child_env(import_root)
    else:
        # Mirrors _build_command minus the ctx arg; each module dep is a --with,
        # so uv provisions them while resolving.
        command = _uv_run_prefix(requirements=_module_requirements(module_dir))
        command += ["--script", str(probe_path), str(module_dir)]
        env = _child_env(import_root)

    completed = subprocess.run(  # noqa: S603 (fixed argv, no shell)
        command,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    stderr = completed.stderr
    # The probe's own error is its last stderr line (uv prints resolution noise
    # before the script runs); keep just that line as the human cause.
    lines = [line for line in stderr.splitlines() if line.strip()]
    error = lines[-1] if lines else None
    return SubprocessStepResult(
        status="completed" if completed.returncode == 0 else "failed",
        returncode=completed.returncode,
        missing_package=_parse_missing_package(stderr),
        error=error,
        stderr=stderr,
    )
