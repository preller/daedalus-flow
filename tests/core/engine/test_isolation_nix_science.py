"""numpy and scipy run under nix and uv isolation with no LD_LIBRARY_PATH shim.

Both runs scrub the variable first; only the nix path stamps ``DAE_ISOLATION=nix``.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from daedalus.core.engine.isolation import NixStrategy

_FIXTURE_LABS = Path(__file__).parents[2] / "fixtures" / "labs"

pytestmark = [
    pytest.mark.skipif(
        not NixStrategy().available(),
        reason="this host cannot build nix flakes (NixStrategy.available() is False)",
    ),
    pytest.mark.integration,
]


def _copy_science(dest_parent: Path) -> Path:
    src = _FIXTURE_LABS / "science_nix"
    dest = dest_parent / "science_nix"
    shutil.copytree(src, dest, ignore=shutil.ignore_patterns("__pycache__"))
    return dest


def _run(lab: Path, *, isolation: str):
    from daedalus.core.engine import LabConfig, LocalEngine
    from daedalus.core.recipe import build_plan, load_recipe

    spec = load_recipe(lab / "lab.yaml")
    plan = build_plan(spec, lab)
    config = LabConfig(
        lab_name="science_nix",
        lab_dir=lab,
        seed=0,
        output_root=lab / "dae-outputs",
        max_workers=spec.max_workers,
        isolation=isolation,
    )
    return LocalEngine().execute_dag(plan, config=config)


def _result(lab: Path) -> dict:
    return json.loads(next(lab.glob(".daedalus/**/result.json")).read_text())


def test_nix_science_runs_with_no_ld_library_path_shim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, require_nix_build: None
) -> None:
    # Scrub the shim, then run under nix: the closure carries its own libs.
    monkeypatch.delenv("LD_LIBRARY_PATH", raising=False)
    lab = _copy_science(tmp_path)

    result = _run(lab, isolation="nix")

    assert result.status == "completed", result.error
    report = _result(lab)
    # The child ran without the shim and still solved the system.
    assert report["ld_library_path_set"] is False
    assert report["isolation_marker"] == "nix"
    assert report["residual_norm"] == pytest.approx(0.0, abs=1e-9)
    assert report["solution"] == pytest.approx([2.0, 3.0])


def test_uv_science_runs_shim_free_on_the_standalone_interpreter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Same scrub under uv. The uv-managed standalone interpreter loads the manylinux
    # wheels against the host glibc, where the ambient nix python needed the shim.
    if shutil.which("uv") is None:
        pytest.skip("the uv backend needs uv")
    monkeypatch.delenv("LD_LIBRARY_PATH", raising=False)
    lab = _copy_science(tmp_path)

    result = _run(lab, isolation="uv")

    assert result.status == "completed", result.error
    report = _result(lab)
    # The uv child ran without the shim and still solved the system.
    assert report["ld_library_path_set"] is False
    # the uv path stamps no nix marker, which keeps the strategies distinct.
    assert report["isolation_marker"] is None
    assert report["residual_norm"] == pytest.approx(0.0, abs=1e-9)
    assert report["solution"] == pytest.approx([2.0, 3.0])
