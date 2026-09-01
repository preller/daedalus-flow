"""sibling_collectors and wide4_join end to end through the installed ``dae``.

Expected values are walk-shape literals or user-side artifacts, not engine internals.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from tests.journey._journey import (
    _copy_fixture_lab,
    _dae,
    _only_flow,
)

pytestmark = pytest.mark.e2e


# sibling_collectors: the exoplanet shape at M=1 (three same-group sibling
# walk_collectors marked -(8)-(9)-(10)-, collectors mint zero walks).
_SIBLING_COLLECTORS_WALK_LINES = [
    "Full:  1-2-3-(4,5,6,7)-[8,9,10]-11-12",
    "Walks: 4",
    "  walk_1: 1-2-3-4-(8)-(9)-(10)-11-12",
    "  walk_2: 1-2-3-5-(8)-(9)-(10)-11-12",
    "  walk_3: 1-2-3-6-(8)-(9)-(10)-11-12",
    "  walk_4: 1-2-3-7-(8)-(9)-(10)-11-12",
]


def _marker_walk_id(step_dir: Path) -> str:
    """The internal walk token a native step recorded in its marker.json."""
    walk_id: str = json.loads((step_dir / "marker.json").read_text())["walk_id"]
    return walk_id


def test_sibling_collectors_runs_end_to_end_through_installed_binary(
    tmp_path: Path,
) -> None:
    """The three sibling collectors share the w2 token in their .daedalus/ dirs."""
    lab = _copy_fixture_lab("sibling_collectors", tmp_path)

    vexit, vcode, vstdout = _dae(lab, "lab", "visualize")
    assert (vexit, vcode) == (0, "dae.lab.visualize.ok"), vstdout
    sib = json.loads(vstdout)["data"]  # unwrap the envelope
    assert sib["token_walk_lines"] == _SIBLING_COLLECTORS_WALK_LINES, vstdout

    rexit, rcode, rstdout = _dae(lab, "lab", "run")
    assert (rexit, rcode) == (0, "dae.lab.run.ok"), rstdout
    assert json.loads(rstdout)["data"]["status"] == "completed", rstdout

    flow = _only_flow(lab)
    store = lab / ".daedalus"
    flight_walks = flow / "flights" / "flight_1" / "walks"
    # the three collectors mint zero walks: each run-once dir under .daedalus/w2/
    # (`NN` is the static plan index) records the same w2 token.
    for native, mirror in (
        ("w2/08_coll_a", "walk_1/05_coll_a"),
        ("w2/09_coll_b", "walk_2/05_coll_b"),
        ("w2/10_coll_c", "walk_3/05_coll_c"),
    ):
        assert _marker_walk_id(store / native) == "w2"
        # the config walk-dir mirror is a manifest-free byte copy (self-containment).
        mirror_dir = flight_walks / mirror
        assert (mirror_dir / "marker.json").exists()
        assert not (mirror_dir / "dae-manifest.json").exists()


def test_wide4_join_mid_walk_failure_holds_the_collector_barrier(
    tmp_path: Path,
) -> None:
    """A failed branch leaves join submitted, siblings completed and no final/."""
    lab = _copy_fixture_lab("wide4_join", tmp_path)
    # break one branch module; its entry raises at run time.
    (lab / "modules" / "b_a" / "main.py").write_text(
        "import daedalus.flow as dae\n\n\n"
        "@dae.entry\n"
        "def run(ctx: dae.FlowContext) -> None:\n"
        '    raise RuntimeError("injected mid-walk failure")\n'
    )

    rexit, rcode, _ = _dae(lab, "lab", "run")
    assert (rexit, rcode) == (1, "dae.lab.run.failed")

    flow = _only_flow(lab)
    record = json.loads((flow / "dae-flow.json").read_text())
    status = {s["step_id"]: s["status"] for s in record["steps"]}
    assert status["b_a@w2"] == "failed"
    assert status["b_b@w3"] == "completed"
    assert status["b_c@w4"] == "completed"
    assert status["b_d@w5"] == "completed"
    # the barrier held; the collector never dispatched on the failed group.
    assert status["join@w1"] == "submitted"
    assert not (flow / "final").exists()


def test_wide4_join_missing_module_dir_is_parse_error_then_invalid(
    tmp_path: Path,
) -> None:
    """A deleted module dir is parse_error on validate and invalid on run."""
    lab = _copy_fixture_lab("wide4_join", tmp_path)
    shutil.rmtree(lab / "modules" / "b_b")
    assert _dae(lab, "lab", "validate")[:2] == (1, "dae.lab.validate.parse_error")
    assert _dae(lab, "lab", "run")[:2] == (2, "dae.lab.run.invalid")


def test_wide4_join_rerun_claims_a_fresh_flow_id(tmp_path: Path) -> None:
    """A second run into the same cwd claims a fresh flow id; trees are disjoint."""
    lab = _copy_fixture_lab("wide4_join", tmp_path)
    assert _dae(lab, "lab", "run")[:2] == (0, "dae.lab.run.ok")
    assert _dae(lab, "lab", "run")[:2] == (0, "dae.lab.run.ok")
    flows = sorted(p for p in (lab / "dae-outputs" / "flows").iterdir() if p.is_dir())
    assert len(flows) == 2, flows
