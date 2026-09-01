"""diamond_join and diamond_repeat end to end through the installed ``dae``.

The expected walk blocks and trees are hand-written literals, not engine output.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.journey._journey import (
    _copy_fixture_lab,
    _dae,
    _data_hashes,
    _data_paths,
    _only_flow,
)

pytestmark = pytest.mark.e2e


# diamond_join is a fixture lab, not a scaffolder name, so the journey copies
# its bundle to tmp_path; dae-outputs/ must never land in the installed wheel.

# The flight-free Full line and numbered Walks block: seed forks to left and
# right, both collected at join, the shared sink.
_DIAMOND_JOIN_WALK_LINES = [
    "Full:  1-(2,3)-4",
    "Walks: 2",
    "  walk_1: 1-2-(4)",
    "  walk_2: 1-3-(4)",
]

# seed and join are flow-scope natives; left and right are native under their
# walk dir, which also holds copies of 01_seed and 04_join. dae-* manifests are
# excluded since their bytes carry timestamps; the data files are the contract.
_DIAMOND_JOIN_DATA_PATHS = [
    "final/joined.json",
    "walks/walk_1/01_seed/value.json",
    "walks/walk_1/02_left/value.json",
    "walks/walk_1/03_join/joined.json",
    "walks/walk_2/01_seed/value.json",
    "walks/walk_2/02_right/value.json",
    "walks/walk_2/03_join/joined.json",
]

# Each walk record carries the internal 5-tuple plus user_walk (walk_J, null on
# the root walk w1). The visualize payload always emits user_walk; the on-disk
# record omits it when null, so the root row differs between the two constants.
_DIAMOND_JOIN_VISUALIZE_WALKS = [
    {
        "walk_id": "w1",
        "flight_id": None,
        "parent_walk": None,
        "born_at": None,
        "branch_module": None,
        "user_walk": None,
    },
    {
        "walk_id": "w2",
        "flight_id": None,
        "parent_walk": "w1",
        "born_at": "seed",
        "branch_module": "left",
        "user_walk": "walk_1",
    },
    {
        "walk_id": "w3",
        "flight_id": None,
        "parent_walk": "w1",
        "born_at": "seed",
        "branch_module": "right",
        "user_walk": "walk_2",
    },
]

# On disk, the root walk omits user_walk; the branch walks carry it.
_DIAMOND_JOIN_RECORD_WALKS = [
    {k: v for k, v in row.items() if not (k == "user_walk" and v is None)}
    for row in _DIAMOND_JOIN_VISUALIZE_WALKS
]

# steps[] keyed by instance id <module>@w<id>.
_DIAMOND_JOIN_INSTANCE_IDS = ["seed@w1", "left@w2", "right@w3", "join@w1"]


def test_diamond_join_runs_end_to_end_through_installed_binary(tmp_path: Path) -> None:
    """The walk block, the tree, the flow record and the run code are literals."""
    lab = _copy_fixture_lab("diamond_join", tmp_path)

    # (i) the visualize walk-list block, byte-for-byte.
    vexit, vcode, vstdout = _dae(lab, "lab", "visualize")
    assert (vexit, vcode) == (0, "dae.lab.visualize.ok"), vstdout
    vpayload = json.loads(vstdout)["data"]  # unwrap the envelope
    assert vpayload["token_walk_lines"] == _DIAMOND_JOIN_WALK_LINES, vstdout
    assert vpayload["walks"] == _DIAMOND_JOIN_VISUALIZE_WALKS, vstdout

    # (iv) the run resolves to the ok code (exit 0).
    rexit, rcode, rstdout = _dae(lab, "lab", "run")
    assert (rexit, rcode) == (0, "dae.lab.run.ok"), rstdout

    # (iii) every instance completed; a missing branch dir would crash join or
    # leave it pending.
    rpayload = json.loads(rstdout)["data"]  # unwrap the envelope
    assert rpayload["status"] == "completed", rstdout
    assert [s["id"] for s in rpayload["steps"]] == _DIAMOND_JOIN_INSTANCE_IDS, rstdout
    assert all(s["status"] == "completed" for s in rpayload["steps"]), rstdout

    flow = _only_flow(lab)

    # (ii) the on-disk self-contained copy tree: natives +
    # per-walk copies + final/.
    assert _data_paths(flow) == _DIAMOND_JOIN_DATA_PATHS

    # the per-walk copies are byte mirrors and carry no dae-manifest.json.
    for copy_dir in ("walks/walk_1/01_seed", "walks/walk_1/03_join"):
        assert (flow / copy_dir / "value.json").exists() or (
            flow / copy_dir / "joined.json"
        ).exists()
        assert not (flow / copy_dir / "dae-manifest.json").exists()

    # joined.json carries both left and right values, so the collector received
    # both branch dirs in walk_inputs.
    joined = json.loads((flow / "final" / "joined.json").read_text())
    assert set(joined["per_branch"]) == {"left", "right"}, joined

    # (iii) the dae-flow.json walk records + instance-keyed steps. user_walk on the
    # branch walks is the v3 marker; per-step timing then bumps the record to v4.
    record = json.loads((flow / "dae-flow.json").read_text())
    assert record["format_version"] == 4, record
    assert record["status"] == "completed", record
    assert record["walks"] == _DIAMOND_JOIN_RECORD_WALKS, record
    assert [s["step_id"] for s in record["steps"]] == _DIAMOND_JOIN_INSTANCE_IDS, record


@pytest.mark.parametrize("fixture", ["diamond_join", "sibling_collectors"])
def test_rerun_is_byte_invariant_at_k1(fixture: str, tmp_path: Path) -> None:
    """K=1 is a total order over instance ids, so two runs give identical trees."""
    lab_a = _copy_fixture_lab(fixture, tmp_path / "a")
    lab_b = _copy_fixture_lab(fixture, tmp_path / "b")
    assert _dae(lab_a, "lab", "run")[:2] == (0, "dae.lab.run.ok")
    assert _dae(lab_b, "lab", "run")[:2] == (0, "dae.lab.run.ok")

    flow_a, flow_b = _only_flow(lab_a), _only_flow(lab_b)

    # identical tree (sorted relative data paths) and identical data-file bytes.
    assert _data_paths(flow_a) == _data_paths(flow_b)
    assert _data_hashes(flow_a) == _data_hashes(flow_b)


# diamond_repeat has two terminal branches, so there is no (N) marker and no
# flow final/. The repeated sink d is a per-walk member of the Full line.
_DIAMOND_REPEAT_WALK_LINES = [
    "Full:  1-(2-4,3-4)",
    "Walks: 2",
    "  walk_1: 1-2-4",
    "  walk_2: 1-3-4",
]
_DIAMOND_REPEAT_VISUALIZE_WALKS = [
    {
        "walk_id": "w1",
        "flight_id": None,
        "parent_walk": None,
        "born_at": None,
        "branch_module": None,
        "user_walk": None,
    },
    {
        "walk_id": "w2",
        "flight_id": None,
        "parent_walk": "w1",
        "born_at": "seed",
        "branch_module": "left",
        "user_walk": "walk_1",
    },
    {
        "walk_id": "w3",
        "flight_id": None,
        "parent_walk": "w1",
        "born_at": "seed",
        "branch_module": "right",
        "user_walk": "walk_2",
    },
]
# On disk the root walk omits user_walk.
_DIAMOND_REPEAT_RECORD_WALKS = [
    {k: v for k, v in row.items() if not (k == "user_walk" and v is None)}
    for row in _DIAMOND_REPEAT_VISUALIZE_WALKS
]
# d repeats per walk (d@w2, d@w3), so the steps are keyed by instance.
_DIAMOND_REPEAT_INSTANCE_IDS = ["seed@w1", "left@w2", "right@w3", "d@w2", "d@w3"]
_DIAMOND_REPEAT_DATA_PATHS = [
    "walks/walk_1/01_seed/marker.json",
    "walks/walk_1/02_left/marker.json",
    "walks/walk_1/03_d/marker.json",
    "walks/walk_2/01_seed/marker.json",
    "walks/walk_2/02_right/marker.json",
    "walks/walk_2/03_d/marker.json",
]


def test_diamond_repeat_runs_end_to_end_through_installed_binary(
    tmp_path: Path,
) -> None:
    """Module d appears once per walk dir, each a native with its own derived seed."""
    lab = _copy_fixture_lab("diamond_repeat", tmp_path)

    # (i) the visualize block + the lineage records carrying the user_walk bridge.
    vexit, vcode, vstdout = _dae(lab, "lab", "visualize")
    assert (vexit, vcode) == (0, "dae.lab.visualize.ok"), vstdout
    vpayload = json.loads(vstdout)["data"]  # unwrap the envelope
    assert vpayload["token_walk_lines"] == _DIAMOND_REPEAT_WALK_LINES, vstdout
    assert vpayload["walks"] == _DIAMOND_REPEAT_VISUALIZE_WALKS, vstdout

    # (iv) the run resolves ok; (iii) every per-walk instance completed.
    rexit, rcode, rstdout = _dae(lab, "lab", "run")
    assert (rexit, rcode) == (0, "dae.lab.run.ok"), rstdout
    rpayload = json.loads(rstdout)["data"]  # unwrap the envelope
    assert rpayload["status"] == "completed", rstdout
    assert [s["id"] for s in rpayload["steps"]] == _DIAMOND_REPEAT_INSTANCE_IDS, rstdout
    assert all(s["status"] == "completed" for s in rpayload["steps"]), rstdout

    flow = _only_flow(lab)

    # (ii) the self-contained per-walk tree: two native 04_d dirs, no flow final/.
    assert _data_paths(flow) == _DIAMOND_REPEAT_DATA_PATHS
    assert not (flow / "final").exists()

    # walk_1's d (d@w2) and walk_2's d (d@w3) are distinct runs with distinct
    # seeds, visible in their per-config copies (03_d).
    seed_1 = json.loads((flow / "walks/walk_1/03_d/marker.json").read_text())["seed"]
    seed_2 = json.loads((flow / "walks/walk_2/03_d/marker.json").read_text())["seed"]
    assert seed_1 != seed_2
    # the config copies carry no manifest; the manifests live in .daedalus/.
    assert not (flow / "walks/walk_1/01_seed/dae-manifest.json").exists()
    assert not (flow / "walks/walk_1/03_d/dae-manifest.json").exists()

    # (iii) lineage records + instance-keyed steps; user_walk is the v3 marker and
    # per-step timing then bumps the record to v4.
    record = json.loads((flow / "dae-flow.json").read_text())
    assert record["format_version"] == 4, record
    assert record["walks"] == _DIAMOND_REPEAT_RECORD_WALKS, record
    step_ids = [s["step_id"] for s in record["steps"]]
    assert step_ids == _DIAMOND_REPEAT_INSTANCE_IDS, record
    # walk_J labels are positional and bump on a lab edit, so this pins the
    # stable triple (flight_id, born_at, branch_module), not the user_walk label.
    w2 = next(w for w in record["walks"] if w["walk_id"] == "w2")
    assert (w2["flight_id"], w2["born_at"], w2["branch_module"]) == (
        None,
        "seed",
        "left",
    )
