"""Copy layout of the diamond_join and linear_smoke labs in the nested run tree.

Walk dirs are byte copies; only the run-once scope dir in ``.daedalus/`` has a manifest.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.core.engine._copy_layout import (
    _copy_lab,
    _daedalus_dir,
    _data_paths,
    _manifest_dirs,
    _run,
    _run_once_dirs,
)

pytestmark = pytest.mark.integration


def test_diamond_join_nested_copy_tree(tmp_path: Path) -> None:
    """Two walks of byte copies, each numbered 01..03 locally, plus final/."""
    plan_lab = _copy_lab("diamond_join", tmp_path)
    _result, flow = _run(plan_lab, "diamond_join")

    assert _data_paths(flow) == [
        "final/joined.json",
        "walks/walk_1/01_seed/value.json",
        "walks/walk_1/02_left/value.json",
        "walks/walk_1/03_join/joined.json",
        "walks/walk_2/01_seed/value.json",
        "walks/walk_2/02_right/value.json",
        "walks/walk_2/03_join/joined.json",
    ]
    # the user-facing flow tree is copies-only: no authoritative step dirs at the
    # flow root, no old flat walks/w<id>/, no output/.
    assert not (flow / "output").exists()
    assert not (flow / "walks" / "w1").exists()
    assert _manifest_dirs(flow) == []
    # the run-once authorities live in .daedalus/, partitioned by token.
    assert _run_once_dirs(plan_lab) == [
        "w1/01_seed",
        "w1/04_join",
        "w2/02_left",
        "w3/03_right",
    ]


def test_diamond_join_natives_carry_manifest_copies_do_not(tmp_path: Path) -> None:
    """Each of the four instances has one manifest in .daedalus/; copies have none."""
    plan_lab = _copy_lab("diamond_join", tmp_path)
    _result, flow = _run(plan_lab, "diamond_join")

    # exactly the four instances are authoritative in the run-once store.
    assert _run_once_dirs(plan_lab) == [
        "w1/01_seed",
        "w1/04_join",
        "w2/02_left",
        "w3/03_right",
    ]
    # every config walk-dir copy holds data but no dae-* record.
    for copy_dir in (
        "walks/walk_1/01_seed",
        "walks/walk_1/02_left",
        "walks/walk_1/03_join",
        "walks/walk_2/01_seed",
        "walks/walk_2/02_right",
        "walks/walk_2/03_join",
    ):
        assert (flow / copy_dir).is_dir()
        assert not (flow / copy_dir / "dae-manifest.json").exists()
        assert not any(p.name.startswith("dae-") for p in (flow / copy_dir).iterdir())


def test_walk_collector_reads_authoritative_tails(tmp_path: Path) -> None:
    """join's ctx.walk_inputs maps walk_J to the run-once tail dirs in .daedalus/."""
    from tests.core.engine._local_engine import _build_run_plan_for_test

    plan_lab = _copy_lab("diamond_join", tmp_path)
    _run(plan_lab, "diamond_join")
    run = _build_run_plan_for_test(plan_lab)

    inputs = run.walk_input_dirs("join@w1")
    assert set(inputs) == {"walk_1", "walk_2"}
    # the tails are the run-once dirs in .daedalus/, never the copies.
    assert inputs["walk_1"].as_posix().endswith(".daedalus/w2/02_left")
    assert inputs["walk_2"].as_posix().endswith(".daedalus/w3/03_right")
    # the tails carry a manifest.
    assert inputs["walk_1"].joinpath("dae-manifest.json").exists()
    assert inputs["walk_2"].joinpath("dae-manifest.json").exists()


def test_diamond_join_join_sums_both_branches(tmp_path: Path) -> None:
    """The collector still receives both branches end to end (11 + 101 = 112)."""
    plan_lab = _copy_lab("diamond_join", tmp_path)
    _result, flow = _run(plan_lab, "diamond_join")
    # the flow result final/ mirrors the sink output (the join).
    joined = json.loads((flow / "final" / "joined.json").read_text())
    assert joined["sum"] == 112
    assert joined["per_branch"] == {"left": 11, "right": 101}
    # final/ is a byte mirror of the authoritative run-once join, carrying no record.
    assert (flow / "final" / "joined.json").read_bytes() == (
        _daedalus_dir(plan_lab) / "w1" / "04_join" / "joined.json"
    ).read_bytes()
    assert not (flow / "final" / "dae-manifest.json").exists()


def test_linear_smoke_nested_flights_tree(tmp_path: Path) -> None:
    """The one chain is copied under flights/flight_1/walks/walk_1/, plus final/."""
    lab = _copy_lab("linear_smoke", tmp_path)
    _result, flow = _run(lab, "linear_smoke")

    # the flow tree holds copies only.
    assert _manifest_dirs(flow) == []
    assert _data_paths(flow) == [
        "final/run_report.json",
        "flights/flight_1/final/walk_summary.json",
        "flights/flight_1/walks/walk_1/01_emit_ticks/ticks.json",
        "flights/flight_1/walks/walk_1/02_debug_io/ticks.json",
        "flights/flight_1/walks/walk_1/03_sleep_briefly/ticks.json",
        "flights/flight_1/walks/walk_1/04_summarize_walk/walk_summary.json",
        "flights/flight_1/walks/walk_1/05_collect_report/run_report.json",
    ]
    # the five run-once authorities live in .daedalus/, partitioned by token.
    assert _run_once_dirs(lab) == [
        "w1/01_emit_ticks",
        "w1/05_collect_report",
        "w2/02_debug_io",
        "w2/03_sleep_briefly",
        "w2/04_summarize_walk",
    ]
    # per-flight final/ + flow final/ exist; output/ is gone.
    assert (flow / "flights" / "flight_1" / "final").is_dir()
    assert (flow / "final").is_dir()
    assert not (flow / "output").exists()


def test_flight_inputs_is_per_flight_final(tmp_path: Path) -> None:
    """flight_inputs maps flight_1 to flights/flight_1/final, not a raw step dir."""
    from tests.core.engine._local_engine import _build_run_plan_for_test

    lab = _copy_lab("linear_smoke", tmp_path)
    _result, flow = _run(lab, "linear_smoke")
    run = _build_run_plan_for_test(lab)

    flight_inputs = run.flight_input_dirs("collect_report@w1")
    assert set(flight_inputs) == {"flight_1"}
    assert flight_inputs["flight_1"].as_posix().endswith("flights/flight_1/final")
    # that final/ holds the chain tail's data (walk_summary.json) so the
    # collector can read it.
    assert (flow / "flights" / "flight_1" / "final" / "walk_summary.json").exists()


def test_linear_final_dirs_mirror_tails(tmp_path: Path) -> None:
    """final/ dirs are byte mirrors of their run-once tails, with no dae-* file."""
    lab = _copy_lab("linear_smoke", tmp_path)
    _result, flow = _run(lab, "linear_smoke")
    store = _daedalus_dir(lab)

    flight_final = flow / "flights" / "flight_1" / "final"
    assert (flight_final / "walk_summary.json").read_bytes() == (
        store / "w2" / "04_summarize_walk" / "walk_summary.json"
    ).read_bytes()
    assert not (flight_final / "dae-manifest.json").exists()

    flow_final = flow / "final"
    assert (flow_final / "run_report.json").read_bytes() == (
        store / "w1" / "05_collect_report" / "run_report.json"
    ).read_bytes()
    assert not (flow_final / "dae-manifest.json").exists()
