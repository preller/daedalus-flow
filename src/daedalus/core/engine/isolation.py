"""Per-module environment isolation with the ambient, uv and nix strategies.

``IsolationStrategy`` decides how one step's environment is built, apart from
scheduling (``OrchestrationEngine``) and concurrency (``max_workers``). Ambient
runs in-process, uv runs a subprocess provisioned from ``requirements.txt``, and
nix runs a per-module uv2nix flake under ``nix shell``. :func:`resolve_module`
maps a module's preference ladder and the lab policy to one strategy; an unset
policy gives ambient at K=1 and uv at K>1. Only ``step.py`` is imported at top level.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from daedalus.core.engine.step import StepError, execute_step

if TYPE_CHECKING:
    import daedalus.flow as dae

# Written last into a per-module flake dir once its env has been built; its
# presence means a warm store hit awaits launch.
_PROVISIONED_MARKER = ".dae-provisioned"

# A cold uv2nix build can take minutes; the cap only stops a wedged daemon from
# hanging the run forever.
_NIX_BUILD_TIMEOUT_S = 1800

# The capability probe runs a trivial `nix eval` (1 + 1), so a few seconds is
# ample; the cap only guards against a wedged daemon hanging the probe forever.
_NIX_PROBE_TIMEOUT_S = 60

# The file a build failure's full nix builder stream is saved to. The raised
# error stays a short distilled cause plus a pointer here, not the raw dump.
_NIX_LOG_NAME = "nix-build.log"

# Trailing lines kept when a failure log has no `error:` line; nix prints the
# realized cause at the tail when it does not prefix one.
_NIX_LOG_TAIL_LINES = 12


def distill_nix_log(raw: str) -> str:
    """Reduce a raw nix builder stream to the lines that explain a failure.

    Keeps the first ``error:`` line and everything after it, where nix appends its
    own "last N log lines" excerpt; without an ``error:`` line it keeps the tail.
    Empty input yields a short placeholder rather than an exception.
    """
    lines = [line for line in raw.splitlines() if line.strip()]
    if not lines:
        return "(nix produced no diagnostic output)"
    for index, line in enumerate(lines):
        if line.lstrip().startswith("error:"):
            return "\n".join(lines[index:])
    return "\n".join(lines[-_NIX_LOG_TAIL_LINES:])


@runtime_checkable
class IsolationStrategy(Protocol):
    """How one step's environment is built and isolated, apart from scheduling."""

    name: str

    def available(self) -> bool:
        """Whether this strategy can run on the host (the capability probe)."""
        ...

    def provision(self, module_dir: Path) -> None:
        """Prepare the module's environment once, before launch (a no-op for some)."""
        ...

    def launch(self, module_dir: Path, ctx: dae.FlowContext) -> None:
        """Run one instance; raise :class:`StepError` on a non-completed step."""
        ...


class AmbientStrategy:
    """In-process in the active environment, the K=1 default."""

    name = "ambient"

    def available(self) -> bool:
        return True

    def provision(self, module_dir: Path) -> None:
        return None

    def launch(self, module_dir: Path, ctx: dae.FlowContext) -> None:
        execute_step(module_dir, ctx)


class UvStrategy:
    """A uv-provisioned subprocess per step, the K>1 default."""

    name = "uv"

    def available(self) -> bool:
        return shutil.which("uv") is not None

    def provision(self, module_dir: Path) -> None:
        return None

    def launch(self, module_dir: Path, ctx: dae.FlowContext) -> None:
        from daedalus.core.engine.subprocess_runner import (  # noqa: PLC0415 (lazy)
            run_step_subprocess,
        )

        result = run_step_subprocess(module_dir, ctx, requirements=())
        # The launch sidecar is an execution artifact, not lineage; dropping it
        # keeps the on-disk tree byte-identical to the in-process path.
        (Path(ctx.step_output_path) / "dae-context.json").unlink(missing_ok=True)
        if result.status != "completed":
            message = result.error or result.stderr or "subprocess step failed"
            raise StepError(
                message,
                missing_package=result.missing_package,
                returncode=result.returncode,
                stderr=result.stderr,
            )


class NixProvisionError(RuntimeError):
    """``isolation: nix`` could not prepare a module's environment."""


def _flake_cache_root() -> Path:
    """The out-of-repo root for generated per-module flakes, under the user cache."""
    # Kept outside any git work tree, since nix flakes see only git-tracked files
    # and a generated flake inside the repo fails as untracked; the `path:`
    # fetcher copies a cache dir verbatim.
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(
        os.path.expanduser("~"), ".cache"
    )
    return Path(base) / "daedalus" / "nix-flakes"


# Hex chars kept from the content-address digest: 16 hex chars is 64 bits, ample
# to keep distinct build inputs from colliding on one flake dir.
_FLAKE_DIGEST_HEXLEN = 16


def _module_flake_dir(module_dir: Path) -> Path:
    """A module's flake dir, content-addressed by the hash of its build inputs."""
    # Keyed on a shipped flake.nix and flake.lock, the uv.lock and pyproject.toml,
    # or the requirements.txt bytes when there is no lock; a generated lock is
    # network- and time-dependent and stays out of the key.
    parts: list[bytes] = []
    flake = module_dir / "flake.nix"
    if flake.is_file():
        parts.append(b"flake.nix\0" + flake.read_bytes())
        flake_lock = module_dir / "flake.lock"
        if flake_lock.is_file():
            parts.append(b"flake.lock\0" + flake_lock.read_bytes())
    lock = module_dir / "uv.lock"
    pyproject = module_dir / "pyproject.toml"
    if lock.is_file():
        parts.append(b"uv.lock\0" + lock.read_bytes())
    if pyproject.is_file():
        parts.append(b"pyproject.toml\0" + pyproject.read_bytes())
    requirements = module_dir / "requirements.txt"
    if not lock.is_file() and requirements.is_file():
        parts.append(b"requirements.txt\0" + requirements.read_bytes())
    digest = hashlib.sha256(b"\0\0".join(parts)).hexdigest()[:_FLAKE_DIGEST_HEXLEN]
    return _flake_cache_root() / digest


# The generated pyproject's floor. The stock flake's interpreter (pkgs.python3,
# nixpkgs-unstable, about 3.13) must satisfy it; a mismatch fails at build time.
_GENERATED_REQUIRES_PYTHON = "3.12"
# TODO: a per-module python version override.

# `uv lock` resolves from PyPI over the network, and cold metadata fetches
# dominate; it runs once per content, cached behind the marker.
_UV_LOCK_TIMEOUT_S = 300


def _render_generated_pyproject(name: str, specs: list[str]) -> str:
    """A minimal deps-only PEP 621 ``pyproject.toml`` from requirement specs."""
    # No build-system, and [tool.uv] package = false so uv does not build the
    # module itself; uv2nix needs only the resolved deps.
    deps = "".join(f'    "{spec}",\n' for spec in specs)
    return (
        "[project]\n"
        f'name = "{name}"\n'
        'version = "0.0.0"\n'
        f'requires-python = ">={_GENERATED_REQUIRES_PYTHON}"\n'
        "dependencies = [\n"
        f"{deps}"
        "]\n"
        "\n"
        "[tool.uv]\n"
        "package = false\n"
    )


def _run_uv_lock(work_dir: Path) -> None:
    """Run ``uv lock`` in ``work_dir``; failure raises :class:`NixProvisionError`."""
    cmd = ["uv", "lock"]
    try:
        proc = subprocess.run(  # noqa: S603 (PATH uv, fixed argv, no shell)
            cmd,
            cwd=work_dir,
            capture_output=True,
            text=True,
            timeout=_UV_LOCK_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise NixProvisionError(
            f"uv lock for {work_dir} could not run: {error}"
        ) from error
    if proc.returncode != 0:
        raise NixProvisionError(
            f"uv lock failed in {work_dir} (rc={proc.returncode}):\n"
            f"{proc.stderr.strip()}"
        )


def _nix_build(flake_dir: Path, *, log_dir: Path | None = None) -> None:
    """Build ``path:<flake_dir>#default`` once; failure raises the distilled cause."""
    # nix comes from PATH. --no-link warms the store so the launch `nix shell` is
    # a store hit; on failure the full stream goes to log_dir/nix-build.log when
    # log_dir is given and the message points at it.
    cmd = [
        "nix",
        "build",
        f"path:{flake_dir}#default",
        "--no-link",
        "--extra-experimental-features",
        "nix-command flakes",
    ]
    try:
        proc = subprocess.run(  # noqa: S603 (PATH nix, fixed argv, no shell)
            cmd,
            capture_output=True,
            text=True,
            timeout=_NIX_BUILD_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise NixProvisionError(
            f"nix build for {flake_dir} could not run: {error}"
        ) from error
    if proc.returncode != 0:
        saved = _save_nix_log(proc.stderr, log_dir)
        distilled = distill_nix_log(proc.stderr)
        pointer = f"\nfull nix log: {saved}" if saved is not None else ""
        raise NixProvisionError(
            f"nix build failed for {flake_dir} (rc={proc.returncode}):\n"
            f"{distilled}{pointer}"
        )


def _save_nix_log(raw: str, log_dir: Path | None) -> Path | None:
    """Save the raw nix stream under ``log_dir``; ``None`` when unset or unwritable."""
    if log_dir is None:
        return None
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / _NIX_LOG_NAME
        log_path.write_text(raw)
    except OSError:
        return None
    return log_path


class NixStrategy:
    """A per-module nix flake built by uv2nix from the module's own lock."""

    name = "nix"

    def available(self) -> bool:
        """Whether this host can run nix with flakes.

        Requires ``nix`` on ``PATH`` and a working ``nix eval`` with the
        experimental features injected, so a host whose nix.conf omits them passes.
        """
        if shutil.which("nix") is None:
            return False
        # nix is resolved on PATH (a host prerequisite), not a hardcoded path.
        cmd = [
            "nix",
            "eval",
            "--extra-experimental-features",
            "nix-command flakes",
            "--expr",
            "1 + 1",
        ]
        try:
            proc = subprocess.run(  # noqa: S603 (PATH nix, fixed argv, no shell)
                cmd,
                capture_output=True,
                text=True,
                timeout=_NIX_PROBE_TIMEOUT_S,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        return proc.returncode == 0 and proc.stdout.strip() == "2"

    def provision(self, module_dir: Path, *, log_dir: Path | None = None) -> None:
        """Materialize and pre-build the module's nix env once.

        A shipped ``flake.nix`` is built as is, ``pyproject.toml`` plus ``uv.lock``
        use the stock template, and a lone ``requirements.txt`` gets a generated
        lock first. The marker short-circuits; ``log_dir`` takes a failed build's log.
        """
        module_dir = Path(module_dir)
        flake_dir = _module_flake_dir(module_dir)
        if (flake_dir / _PROVISIONED_MARKER).is_file():
            return
        if (module_dir / "flake.nix").is_file():
            self._materialize_own_flake(flake_dir, module_dir, log_dir=log_dir)
            return
        pyproject = module_dir / "pyproject.toml"
        lock = module_dir / "uv.lock"
        if pyproject.is_file() and lock.is_file():
            self._materialize_and_build(
                flake_dir, pyproject=pyproject, lock=lock, log_dir=log_dir
            )
            return
        from daedalus.core.engine.subprocess_runner import (  # noqa: PLC0415 (lazy)
            _module_requirements,
        )

        specs = _module_requirements(module_dir)
        if specs:
            self._generate_and_build(flake_dir, module_dir.name, specs, log_dir=log_dir)
            return
        raise NixProvisionError(
            f"nothing to nixify in {module_dir}: it ships no "
            f"flake.nix, no uv.lock (with pyproject.toml), and no requirements.txt. "
            f"add a uv.lock (run 'uv lock' in the module), a requirements.txt, or a "
            f"flake.nix, or use isolation: uv."
        )

    def launch(self, module_dir: Path, ctx: dae.FlowContext) -> None:
        """Run one instance under the module's nix env; ``StepError`` on failure.

        Provisions first (idempotent), launches the shim with ``nix shell`` through
        :func:`run_step_nix`, drops the launch sidecar so the tree matches the uv and
        ambient paths, and raises :class:`StepError` with ``missing_package`` when set.
        """
        from daedalus.core.engine.subprocess_runner import (  # noqa: PLC0415 (lazy)
            run_step_nix,
        )

        module_dir = Path(module_dir)
        # Save any build-failure log beside this step's output (under the flow dir).
        self.provision(module_dir, log_dir=Path(ctx.step_output_path))
        flake_dir = _module_flake_dir(module_dir)
        result = run_step_nix(
            module_dir, ctx, flake_ref=f"path:{flake_dir}", env_attr="default"
        )
        (Path(ctx.step_output_path) / "dae-context.json").unlink(missing_ok=True)
        if result.status != "completed":
            message = result.error or result.stderr or "nix subprocess step failed"
            raise StepError(
                message,
                missing_package=result.missing_package,
                returncode=result.returncode,
                stderr=result.stderr,
            )

    @staticmethod
    def _materialize_and_build(
        flake_dir: Path, *, pyproject: Path, lock: Path, log_dir: Path | None = None
    ) -> None:
        """Build the stock template beside a module's pyproject + lock."""
        template = Path(__file__).resolve().parent / "nix"
        NixStrategy._stage_build_publish(
            flake_dir,
            {
                "flake.nix": template / "flake.nix",
                "flake.lock": template / "flake.lock",
                "pyproject.toml": pyproject,
                "uv.lock": lock,
            },
            log_dir=log_dir,
        )

    @staticmethod
    def _materialize_own_flake(
        flake_dir: Path, module_dir: Path, *, log_dir: Path | None = None
    ) -> None:
        """Build the module's own flake plus the lock and pyproject files it ships."""
        sources: dict[str, Path] = {"flake.nix": module_dir / "flake.nix"}
        for name in ("flake.lock", "pyproject.toml", "uv.lock"):
            candidate = module_dir / name
            if candidate.is_file():
                sources[name] = candidate
        NixStrategy._stage_build_publish(flake_dir, sources, log_dir=log_dir)

    @staticmethod
    def _generate_and_build(
        flake_dir: Path,
        name: str,
        specs: list[str],
        *,
        log_dir: Path | None = None,
    ) -> None:
        """Generate pyproject and uv.lock from specs in a temp dir, then build."""
        import tempfile  # noqa: PLC0415 (lazy, runtime-only)

        # The lock is generated in a throwaway dir, so the module tree stays a
        # plain requirements-only module; uv lock runs once here, behind the marker.
        template = Path(__file__).resolve().parent / "nix"
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            (work / "pyproject.toml").write_text(
                _render_generated_pyproject(name, specs)
            )
            _run_uv_lock(work)
            NixStrategy._stage_build_publish(
                flake_dir,
                {
                    "flake.nix": template / "flake.nix",
                    "flake.lock": template / "flake.lock",
                    "pyproject.toml": work / "pyproject.toml",
                    "uv.lock": work / "uv.lock",
                },
                log_dir=log_dir,
            )

    @staticmethod
    def _stage_build_publish(
        flake_dir: Path,
        sources: dict[str, Path],
        *,
        log_dir: Path | None = None,
    ) -> None:
        """Stage ``sources``, build, then publish the dir with one ``os.replace``."""
        # A per-process staging dir plus os.replace means two concurrent launches
        # of one module never see a half-written flake dir; the marker is written
        # last, so its presence implies a complete, built dir.
        staging = flake_dir.parent / f".staging-{flake_dir.name}-{os.getpid()}"
        staging.parent.mkdir(parents=True, exist_ok=True)
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir(parents=True)
        try:
            for name, src in sources.items():
                shutil.copy(src, staging / name)
            _nix_build(staging, log_dir=log_dir)
            (staging / _PROVISIONED_MARKER).write_text("ok\n")
            try:
                os.replace(staging, flake_dir)
            except OSError:
                # Another process published an identical flake_dir first; this
                # build already warmed the store, so the staging copy is dropped.
                shutil.rmtree(staging, ignore_errors=True)
        finally:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)


@dataclass(frozen=True)
class ModuleEnv:
    """The host-independent inputs to a module's isolation resolution."""

    module: str
    preference: tuple[str, ...]  # the isolation ladder, strongest first
    has_flake: bool = False
    has_lock: bool = False
    has_requirements: bool = False

    @classmethod
    def from_module_dir(cls, module: str, module_dir: Path) -> ModuleEnv:
        """Build a :class:`ModuleEnv` from the module manifest and the files it ships.

        The recipe import is lazy so ``import yaml`` stays off the engine import path.
        """
        from daedalus.core.recipe import (  # noqa: PLC0415 (lazy, keeps yaml off path)
            read_module_isolation_pref,
        )

        return cls(
            module=module,
            preference=read_module_isolation_pref(module_dir),
            has_flake=(module_dir / "flake.nix").is_file(),
            has_lock=(module_dir / "uv.lock").is_file(),
            has_requirements=(module_dir / "requirements.txt").is_file(),
        )


@dataclass(frozen=True)
class ModuleResolution:
    """The resolved isolation decision for one module, the validate ``--json`` row."""

    module: str
    strategy: str  # realized strategy name, ambient, uv or nix
    downgraded: bool  # ran below its top preference without a ladder fallback
    source: str  # preference, policy or auto-gen
    flake_origin: str | None  # nix provenance; None for non-nix or nothing to nixify


# Strength order none < uv < nix. ambient shares none's strength, so forcing
# ambient onto a uv- or nix-preferring module is the same downgrade as forcing none.
_ISOLATION_STRENGTH = {"none": 0, "ambient": 0, "uv": 1, "nix": 2}


def _pref_satisfiable(entry: str, env: ModuleEnv) -> bool:
    """Whether a ladder entry is backed by the files the module ships."""
    if entry == "none":
        return True
    if entry == "uv":
        return env.has_requirements or env.has_lock
    return env.has_flake or env.has_lock or env.has_requirements


def _realize(preference_value: str, max_workers: int) -> str:
    """A preference value's strategy name; ``none`` is ambient at K=1 and uv above."""
    if preference_value == "none":
        return "ambient" if max_workers == 1 else "uv"
    return preference_value


def _flake_origin(env: ModuleEnv) -> str | None:
    """The nix input a module builds from, or ``None`` with nothing to nixify."""
    if env.has_flake:
        return "own-flake"
    if env.has_lock:
        return "generated-from-lock"
    if env.has_requirements:
        return "generated-from-requirements"
    return None


def _is_downgrade(preference: tuple[str, ...], resolved_strategy: str) -> bool:
    """Weaker than the top preference and absent from the ladder."""
    resolved = _ISOLATION_STRENGTH[resolved_strategy]
    top = _ISOLATION_STRENGTH[preference[0]]
    sanctioned = resolved in {_ISOLATION_STRENGTH[entry] for entry in preference}
    return resolved < top and not sanctioned


def _strategy_and_source(
    env: ModuleEnv, policy: str | None, max_workers: int
) -> tuple[str, bool, str]:
    """Resolve (strategy name, downgraded, source) before the nix flake overlay."""
    # The explicit comparison lets the type checker narrow `policy` to str past
    # this guard; the ambient and uv branch below needs a real str.
    if policy is None or policy == "auto":
        chosen = next(
            (e for e in env.preference if _pref_satisfiable(e, env)),
            env.preference[0],
        )
        return _realize(chosen, max_workers), False, "preference"
    if policy == "nix":
        return "nix", False, "policy"
    # ambient / uv: force lab-wide, flagging a non-sanctioned downgrade.
    return policy, _is_downgrade(env.preference, policy), "policy"


def resolve_module(
    env: ModuleEnv, policy: str | None, max_workers: int
) -> ModuleResolution:
    """Resolve one module's isolation, purely and host-independently.

    ``policy`` is the lab policy (``None``/``auto`` honor the ladder; ``ambient``/
    ``uv``/``nix`` force lab-wide). A nix resolution gets its ``flake_origin``; a
    generated flake flips ``source`` to ``auto-gen``.
    """
    strategy, downgraded, source = _strategy_and_source(env, policy, max_workers)
    flake_origin = _flake_origin(env) if strategy == "nix" else None
    if flake_origin is not None and flake_origin.startswith("generated"):
        source = "auto-gen"
    return ModuleResolution(
        module=env.module,
        strategy=strategy,
        downgraded=downgraded,
        source=source,
        flake_origin=flake_origin,
    )


def resolve_plan(
    modules: Sequence[ModuleEnv], policy: str | None, max_workers: int
) -> list[ModuleResolution]:
    """Resolve every module of a lab to its isolation decision, order preserved.

    Both the run path (``strategy_for(resolution.strategy)``) and ``validate``
    consume the result.
    """
    return [resolve_module(env, policy, max_workers) for env in modules]


def strategy_for(name: str) -> IsolationStrategy:
    """Build the :class:`IsolationStrategy` for a resolved strategy name."""
    if name == "ambient":
        return AmbientStrategy()
    if name == "uv":
        return UvStrategy()
    if name == "nix":
        return NixStrategy()
    raise ValueError(f"unknown isolation strategy {name!r}")
