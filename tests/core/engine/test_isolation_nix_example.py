"""Two ``isolation-nix`` example modules pin different pyfiglet versions in one run.

Needs a host that builds nix; the lifecycle checks sit in test_journey_examples.py.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from daedalus.core.engine.isolation import NixStrategy
from tests._helpers import examples_root

pytestmark = [
    pytest.mark.skipif(
        not NixStrategy().available(),
        reason="this host cannot build nix flakes (NixStrategy.available() is False)",
    ),
    pytest.mark.integration,
]


def _run_example(tmp_path: Path):
    from daedalus.core.engine import LabConfig, LocalEngine
    from daedalus.core.recipe import build_plan, load_recipe

    src = examples_root() / "isolation-nix"
    lab = tmp_path / "isolation-nix"
    shutil.copytree(src, lab, ignore=shutil.ignore_patterns("__pycache__"))
    spec = load_recipe(lab / "lab.yaml")
    plan = build_plan(spec, lab)
    config = LabConfig(
        lab_name="isolation-nix",
        lab_dir=lab,
        seed=0,
        output_root=lab / "dae-outputs",
        max_workers=spec.max_workers,
        isolation=spec.isolation,  # nix, from the lab.yaml
    )
    result = LocalEngine().execute_dag(plan, config=config)
    return result, lab


def _reports(lab: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for report in lab.glob(".daedalus/**/report.json"):
        data = json.loads(report.read_text())
        out[data["branch"]] = data
    return out


def test_two_pyfiglet_versions_coexist_per_module(
    tmp_path: Path, require_nix_build: None
) -> None:
    result, lab = _run_example(tmp_path)

    # verify raises when the proof fails, so completion is part of the assertion.
    assert result.status == "completed", result.error

    reports = _reports(lab)
    # Each branch imported the version it pinned, and the two differ.
    assert reports["render_classic"]["imported_pyfiglet_version"] == "1.0.2"
    assert reports["render_modern"]["imported_pyfiglet_version"] == "1.0.4"
    assert reports["render_classic"]["isolation_marker"] == "nix"
    assert reports["render_modern"]["isolation_marker"] == "nix"

    # The verify module's own verdict agrees.
    proof = json.loads(next(lab.glob(".daedalus/**/proof.json")).read_text())
    assert proof["isolation_proven"] is True
    assert proof["the_two_versions_differ"] is True
    assert proof["each_module_got_its_pinned_version"] is True


def test_a_shared_pin_would_not_prove_divergence(
    tmp_path: Path, require_nix_build: None
) -> None:
    # Had both modules imported one version, verify would have raised and the run
    # failed; the versions are distinct, so one env cannot shadow the other.
    _result, lab = _run_example(tmp_path)
    reports = _reports(lab)
    versions = {
        reports["render_classic"]["imported_pyfiglet_version"],
        reports["render_modern"]["imported_pyfiglet_version"],
    }
    assert len(versions) == 2, f"expected two distinct versions, got {versions}"
