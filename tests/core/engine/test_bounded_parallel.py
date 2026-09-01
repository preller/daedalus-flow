"""K=1 in-process and K=4 subprocess runs of diamond_join write the same tree.

Its ``left`` and ``right`` run concurrently at K>=2; the module skips without ``uv``.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

import daedalus.flow as dae

if TYPE_CHECKING:
    from daedalus.core.engine.protocol import ExecutionResult

# Reuse the established lab-run + tree-census idioms from the engine e2e suite
# (tests/ is on sys.path via the default prepend import mode; conftest is imported
# the same way across the suite).
from tests.core.engine._local_engine import (
    _copy_diamond_join,
    _copy_lab,
    _daedalus,
    _only_flow,
    _run_once_dirs,
)

_UV = shutil.which("uv")
pytestmark = [
    pytest.mark.skipif(
        _UV is None, reason="uv launcher not on PATH; K>1 subprocess isolation needs it"
    ),
    pytest.mark.integration,
]

# Timestamps and the measured duration change every run and are not compared.
_VOLATILE_MANIFEST_KEYS = ("started_at", "finished_at", "duration_s")

# The JSON FlowContext handed to the child; an execution artifact, not lineage.
_SUBPROCESS_SIDECAR = "dae-context.json"

# The traceback log of a failed step carries absolute paths and line numbers that
# differ between the two paths; the manifest's error and error_code are compared.
_STEP_ERROR_LOG = "step-error.log"

# The child's teed stdout and stderr; per run, and only on the subprocess path.
_STEP_LOG = "step.log"

# Execution artifacts excluded from the cross-path determinism tree (not lineage).
_EXCLUDED_ARTIFACTS = (_SUBPROCESS_SIDECAR, _STEP_ERROR_LOG, _STEP_LOG)


def _run_diamond_at(
    tmp_path: Path, *, max_workers: int
) -> tuple[ExecutionResult, Path]:
    """Run diamond_join under LocalEngine at a given K; return ``(result, lab)``."""
    from daedalus.core.engine import LabConfig, LocalEngine

    plan, config, lab = _copy_diamond_join(tmp_path)
    config = LabConfig(
        lab_name=config.lab_name,
        lab_dir=config.lab_dir,
        seed=config.seed,
        output_root=config.output_root,
        max_workers=max_workers,
    )
    result = LocalEngine().execute_dag(plan, config=config)
    return result, lab


def _daedalus_canonical(lab: Path) -> dict[str, str]:
    """The .daedalus/ tree by token path, manifests without the volatile fields."""
    store = _daedalus(lab)
    tree: dict[str, str] = {}
    for path in sorted(store.rglob("*")):
        if not path.is_file() or path.name in _EXCLUDED_ARTIFACTS:
            continue
        rel = path.relative_to(store).as_posix()
        if path.name == "dae-manifest.json":
            manifest = json.loads(path.read_text())
            for key in _VOLATILE_MANIFEST_KEYS:
                manifest.pop(key, None)
            tree[f".daedalus/{rel}"] = json.dumps(manifest, sort_keys=True, indent=2)
        else:
            tree[f".daedalus/{rel}"] = path.read_text()
    return tree


def _canonical_tree(lab: Path) -> dict[str, str]:
    """The .daedalus/ tree plus final/, re-keyed off the volatile flow dir."""
    tree = _daedalus_canonical(lab)
    final = _only_flow(lab) / "final"
    for path in sorted(final.rglob("*")):
        if path.is_file() and path.name not in _EXCLUDED_ARTIFACTS:
            tree[f"final/{path.relative_to(final).as_posix()}"] = path.read_text()
    return tree


def test_k1_inprocess_and_k4_subprocess_are_byte_identical(tmp_path: Path) -> None:
    """The data files and manifests match once the volatile fields are dropped."""
    r1, lab1 = _run_diamond_at(tmp_path / "k1", max_workers=1)
    r4, lab4 = _run_diamond_at(tmp_path / "k4", max_workers=4)
    assert r1.status == "completed", r1.error
    assert r4.status == "completed", r4.error

    # The same four instances ran exactly once at both K.
    expected_census = ["w1/01_seed", "w1/04_join", "w2/02_left", "w3/03_right"]
    assert _run_once_dirs(lab1) == expected_census
    assert _run_once_dirs(lab4) == expected_census

    t1, t4 = _canonical_tree(lab1), _canonical_tree(lab4)
    # Same file set first, then the same content modulo the volatile fields.
    assert set(t1) == set(t4), "K=1 and K=4 produced different file sets"
    assert t1 == t4, "K=1 and K=4 diverged on deterministic content"


def test_k4_join_result_matches_k1(tmp_path: Path) -> None:
    """The join sums left (11) and right (101) to 112 at either K."""
    _r1, lab1 = _run_diamond_at(tmp_path / "k1", max_workers=1)
    _r4, lab4 = _run_diamond_at(tmp_path / "k4", max_workers=4)

    def _joined(lab: Path) -> dict[str, object]:
        text = (_daedalus(lab) / "w1" / "04_join" / "joined.json").read_text()
        parsed: dict[str, object] = json.loads(text)
        return parsed

    assert _joined(lab1) == _joined(lab4)
    assert _joined(lab4)["sum"] == 112
    assert _joined(lab4)["per_branch"] == {"left": 11, "right": 101}


def test_k4_routes_every_instance_through_run_step_subprocess(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A spy on run_step_subprocess fires once per instance at K=4, never at K=1."""
    from daedalus.core.engine import subprocess_runner

    real = subprocess_runner.run_step_subprocess
    calls: list[str] = []

    def _spy(module_dir: Path, ctx: dae.FlowContext, **kwargs: object) -> object:
        calls.append(ctx.step_id)
        return real(module_dir, ctx, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(subprocess_runner, "run_step_subprocess", _spy)

    # K=1 stays in-process.
    _run_diamond_at(tmp_path / "k1", max_workers=1)
    assert calls == [], "K=1 must not launch any subprocess"

    # K=4: every one of the four instances ran as a fresh subprocess.
    _run_diamond_at(tmp_path / "k4", max_workers=4)
    assert sorted(calls) == ["join", "left", "right", "seed"]


def test_golden_is_sensitive_to_a_subprocess_divergence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An extra byte written on the subprocess path shows up as a tree difference."""
    from daedalus.core.engine import subprocess_runner

    real = subprocess_runner.run_step_subprocess

    def _perturbing(module_dir: Path, ctx: dae.FlowContext, **kwargs: object) -> object:
        result = real(module_dir, ctx, **kwargs)  # type: ignore[arg-type]
        if ctx.step_id == "join":  # the leaf, so nothing downstream reads it
            joined = Path(ctx.step_output_path) / "joined.json"
            joined.write_text(joined.read_text() + "\n")
        return result

    monkeypatch.setattr(subprocess_runner, "run_step_subprocess", _perturbing)

    _r1, lab1 = _run_diamond_at(tmp_path / "k1", max_workers=1)
    _r4, lab4 = _run_diamond_at(tmp_path / "k4", max_workers=4)
    assert _canonical_tree(lab1) != _canonical_tree(lab4), (
        "the golden's comparison is vacuous: a real subprocess divergence "
        "did not register as a tree difference"
    )


_RAISING_LEFT = (
    "import daedalus.flow as dae\n\n\n"
    "@dae.entry\n"
    "def left(ctx: dae.FlowContext) -> None:\n"
    '    raise RuntimeError("left raised by the test")\n'
)


def _run_failing_diamond_at(
    tmp_path: Path, *, max_workers: int
) -> tuple[ExecutionResult, Path]:
    """Run diamond_join with a raising ``left`` at K; return ``(result, lab)``."""
    from daedalus.core.engine import LabConfig, LocalEngine
    from daedalus.core.recipe import build_plan, load_recipe

    lab = _copy_lab("diamond_join", tmp_path)
    (lab / "modules" / "left" / "main.py").write_text(_RAISING_LEFT)
    spec = load_recipe(lab / "lab.yaml")
    plan = build_plan(spec, lab)
    config = LabConfig(
        lab_name="diamond_join",
        lab_dir=lab,
        seed=0,
        output_root=lab / "dae-outputs",
        max_workers=max_workers,
    )
    result = LocalEngine().execute_dag(plan, config=config)
    return result, lab


def test_k4_failure_drains_the_wave_for_a_deterministic_partial_tree(
    tmp_path: Path,
) -> None:
    """``right`` still completes beside the failing ``left``; ``join`` never runs."""
    r1, lab1 = _run_failing_diamond_at(tmp_path / "k1", max_workers=1)
    r4, lab4 = _run_failing_diamond_at(tmp_path / "k4", max_workers=4)
    assert r1.status == "failed"
    assert r4.status == "failed"

    # seed, the failed left and the completed right all ran; join never became
    # ready. The census is identical at K=1 and K=4.
    expected_census = ["w1/01_seed", "w2/02_left", "w3/03_right"]
    assert _run_once_dirs(lab1) == expected_census
    assert _run_once_dirs(lab4) == expected_census

    for lab in (lab1, lab4):
        left = json.loads(
            (_daedalus(lab) / "w2" / "02_left" / "dae-manifest.json").read_text()
        )
        right = json.loads(
            (_daedalus(lab) / "w3" / "03_right" / "dae-manifest.json").read_text()
        )
        assert left["status"] == "failed"
        # right completed despite its sibling failing in the same wave.
        assert right["status"] == "completed"

    # Byte-identical partial tree (data + manifests modulo the volatile fields).
    assert _daedalus_canonical(lab1) == _daedalus_canonical(lab4)
