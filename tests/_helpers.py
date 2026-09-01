"""Engine-free helpers the test suite imports from ``tests._helpers``.

Runs any module standalone by file path; the only third-party import is daedalus.
"""

from __future__ import annotations

import contextlib
import json
import math
import re
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import daedalus.flow as dae
from daedalus.core.engine import step as _step

# contextlib.chdir (3.11+), bound here so ``from tests._helpers import chdir`` keeps
# working; a ``dae`` run keys its outputs off the cwd.
chdir = contextlib.chdir


def examples_root() -> Path:
    """Return ``src/daedalus/examples/`` as a filesystem ``Path``.

    ``daedalus.core.paths.examples_root()`` returns a Traversable, which cannot
    be staged into; the installed package location gives a concrete path.
    """
    import daedalus.examples as examples_pkg

    return Path(examples_pkg.__file__).parent


def fixtures_root() -> Path:
    """Return ``tests/fixtures/`` as a filesystem ``Path``.

    The test-only labs and modules are not shipped in the wheel, so they are
    addressed relative to this file, not through ``importlib.resources``.
    """
    return Path(__file__).parent / "fixtures"


def load_entry(main_path: Path) -> Callable:
    """Import a module's ``main.py`` by file path and return its entry callable.

    Delegates to :func:`daedalus.core.engine.step.load_entry`, so the harness and
    the engine load steps through one runner; a load failure raises StepError.
    """
    return _step.load_entry(Path(main_path))


def run_module(  # noqa: PLR0913 (one keyword argument per FlowContext field)
    entry: Callable,
    *,
    role: dae.Role,
    output_dir: Path,
    input_dir: Path | None = None,
    walk_inputs: dict[str, Path] | None = None,
    flight_inputs: dict[str, Path] | None = None,
    flight_id: str = "flight_1",
    walk_id: str = "walk_1",
    seed: int = 0,
) -> Path:
    """Build a ``FlowContext``, call ``entry(ctx)`` standalone, return ``output_dir``.

    The output directory is created first, as daedalus does before every call.
    Emitter and transform read ``step_input_path``; aggregators read ``walk_inputs``
    or ``flight_inputs``. Without ``input_dir`` the input path is ``output_dir``.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    ctx = _step.build_context(
        step_id=entry.__name__,
        role=role,
        output_dir=output_dir,
        input_dir=input_dir,
        walk_inputs=walk_inputs,
        flight_inputs=flight_inputs,
        flight_id=flight_id,
        walk_id=walk_id,
        seed=seed,
    )
    entry(ctx)
    return output_dir


def assert_golden_json(produced: Path, expected: Path) -> None:
    """Assert ``produced`` byte-equals ``expected``.

    Goldens are ``json.dumps(obj, indent=2)`` with no trailing newline, as every
    module writes them, so the comparison is on the text, not a parsed structure.
    """
    produced = Path(produced)
    expected = Path(expected)
    actual_text = produced.read_text()
    expected_text = expected.read_text()
    assert actual_text == expected_text, (
        f"golden mismatch:\n  produced: {produced}\n  expected: {expected}"
    )


def _approx_numeric_equal(
    a: float, b: float, rtol: float, atol: float, path: str
) -> None:
    """NaN equals NaN, inf must match sign, anything else goes through isclose."""
    af, bf = float(a), float(b)
    if math.isnan(af) and math.isnan(bf):
        return
    if math.isinf(af) or math.isinf(bf):
        if af == bf:
            return
        raise AssertionError(f"inf mismatch at {path}: {af!r} != {bf!r}")
    if not math.isclose(af, bf, rel_tol=rtol, abs_tol=atol):
        raise AssertionError(f"float mismatch at {path}: {af!r} != {bf!r}")


def _approx_leaf_equal(
    a: object, b: object, rtol: float, atol: float, path: str
) -> None:
    """bool first (an int subclass), int exact, float by isclose, others exact."""
    if isinstance(a, bool) or isinstance(b, bool):
        if type(a) is not type(b) or a != b:
            raise AssertionError(f"bool mismatch at {path}: {a!r} != {b!r}")
        return
    if isinstance(a, int) and isinstance(b, int):
        if a != b:
            raise AssertionError(f"int mismatch at {path}: {a!r} != {b!r}")
        return
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        _approx_numeric_equal(a, b, rtol, atol, path)
        return
    if type(a) is not type(b):
        raise AssertionError(
            f"type mismatch at {path}: {type(a).__name__} != {type(b).__name__}"
        )
    if a != b:
        raise AssertionError(f"value mismatch at {path}: {a!r} != {b!r}")


def _approx_recurse_dict(a: dict, b: dict, rtol: float, atol: float, path: str) -> None:
    """Recurse two dicts in lockstep; the key sets must match."""
    if set(a) != set(b):
        raise AssertionError(
            f"key-set mismatch at {path}: produced={sorted(a)} expected={sorted(b)}"
        )
    for key, a_value in a.items():
        child = f"{path}.{key}" if path else str(key)
        _approx_recurse(a_value, b[key], rtol, atol, child)


def _approx_recurse_list(a: list, b: list, rtol: float, atol: float, path: str) -> None:
    """Recurse two lists in lockstep; equal length, pairwise in order."""
    if len(a) != len(b):
        raise AssertionError(f"list-length mismatch at {path}: {len(a)} != {len(b)}")
    for i, (ai, bi) in enumerate(zip(a, b, strict=True)):
        _approx_recurse(ai, bi, rtol, atol, f"{path}[{i}]")


def _approx_recurse(a: object, b: object, rtol: float, atol: float, path: str) -> None:
    """Recurse two parsed JSON values in lockstep (dict/list/leaf)."""
    if isinstance(a, dict) or isinstance(b, dict):
        if not (isinstance(a, dict) and isinstance(b, dict)):
            raise AssertionError(f"type mismatch at {path}: dict vs non-dict")
        _approx_recurse_dict(a, b, rtol, atol, path)
        return
    if isinstance(a, list) or isinstance(b, list):
        if not (isinstance(a, list) and isinstance(b, list)):
            raise AssertionError(f"type mismatch at {path}: list vs non-list")
        _approx_recurse_list(a, b, rtol, atol, path)
        return
    _approx_leaf_equal(a, b, rtol, atol, path)


def assert_golden_json_approx(
    produced: Path,
    expected: Path,
    *,
    rtol: float = 1e-9,
    atol: float = 1e-12,
) -> None:
    """Assert ``produced`` matches ``expected`` structurally, floats within tolerance.

    Both files are parsed and walked in lockstep: key sets, list lengths and
    non-float leaves must match exactly; only float leaves use ``math.isclose``.
    The tolerance absorbs last-digit drift from a numpy or scipy bump and not more.
    """
    a = json.loads(Path(produced).read_text())
    b = json.loads(Path(expected).read_text())
    _approx_recurse(a, b, rtol, atol, "")


_FIXTURE_LABS = fixtures_root() / "labs"


def _copy_lab(name: str, dest_parent: Path) -> Path:
    """Copy a ``fixtures/labs/<name>`` tree into ``dest_parent`` (skip __pycache__)."""
    dest = dest_parent / name
    shutil.copytree(
        _FIXTURE_LABS / name, dest, ignore=shutil.ignore_patterns("__pycache__")
    )
    return dest


def _copy_example(name: str, dest_parent: Path) -> Path:
    """Copy a shipped gallery example (``examples/<name>``), not a fixture lab."""
    dest = dest_parent / name
    shutil.copytree(
        examples_root() / name,
        dest,
        ignore=shutil.ignore_patterns("__pycache__", "dae-outputs"),
    )
    return dest


def _write_module(mod_dir: Path, body: str, *, role: str = "transform") -> Path:
    """Stage a module dir with a ``dae-module.yaml`` role and a ``main.py`` body."""
    mod_dir.mkdir(parents=True, exist_ok=True)
    (mod_dir / "dae-module.yaml").write_text(f"role: {role}\n")
    (mod_dir / "main.py").write_text(body)
    return mod_dir


def _step_ctx(
    *, output_dir: Path, input_dir: Path, role: dae.Role, seed: int
) -> dae.FlowContext:
    """A FlowContext wired like the engine wires a linear transform/emitter."""
    return _step.build_context(
        step_id=output_dir.name,
        role=role,
        output_dir=output_dir,
        input_dir=input_dir,
        seed=seed,
    )


def _run_cli_in(path: Path, *args: str) -> tuple[int, str | None]:
    """Run ``dae --json`` with cwd at ``path``; return (exit_code, code or None)."""
    from typer.testing import CliRunner

    from daedalus.cli.app import app

    runner = CliRunner()
    with chdir(path):
        result = runner.invoke(app, ["--json", *args], prog_name="dae")
    code: str | None = None
    if result.stdout.strip():
        with contextlib.suppress(json.JSONDecodeError):
            code = json.loads(result.stdout).get("code")
    return result.exit_code, code


def _daedalus(lab: Path) -> Path:
    """The run-once staging store for a lab (``.daedalus/`` beside ``dae-outputs/``)."""
    return lab / ".daedalus"


def _run_once_dirs(lab: Path) -> list[str]:
    """Sorted ``<token>/<NN>_<module>`` run-once dirs under ``.daedalus/``."""
    store = _daedalus(lab)
    return sorted(
        p.parent.relative_to(store).as_posix() for p in store.rglob("dae-manifest.json")
    )


def copy_parallel_example(dest: Path, *, engine: str, max_workers: int) -> Path:
    """Copy the ``parallel`` example into ``dest``, pinning engine + max_workers.

    The brancher example (split -> four stat_* branch walks -> combine) carries a
    per-module requirements.txt, so a K>1 copy exercises the provisioning path, not
    just in-process serial. Shared by the engine timing and conformance tests.
    """
    lab = dest / f"parallel_{engine}_k{max_workers}"
    shutil.copytree(
        examples_root() / "parallel",
        lab,
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    text = (lab / "lab.yaml").read_text()
    text = re.sub(r"^engine:.*$", f"engine: {engine}", text, count=1, flags=re.M)
    text = re.sub(
        r"^max_workers:.*$", f"max_workers: {max_workers}", text, count=1, flags=re.M
    )
    (lab / "lab.yaml").write_text(text)
    return lab


def run_cli_json(lab: Path, *argv: str) -> dict[str, Any]:
    """Run ``dae --json <argv>`` with cwd inside ``lab``; assert exit 0, return payload.

    The success-path sibling of :func:`_run_cli_in` (which returns the
    ``(exit_code, code)`` pair for usage-error tests). ``CliRunner`` is imported
    lazily to keep this module's import path daedalus-only.
    """
    from typer.testing import CliRunner

    from daedalus.cli.app import app

    runner = CliRunner()
    with chdir(lab):
        result = runner.invoke(app, ["--json", *argv], prog_name="dae")
    assert result.exit_code == 0, result.output
    return json.loads(result.output)
