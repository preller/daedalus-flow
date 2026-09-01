"""Copy layout of the inline emitter+brancher lab, copy atomicity and rerun determinism.

Walk dirs are byte copies; only the run-once scope dir in ``.daedalus/`` has a manifest.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests._helpers import _write_module
from tests.core.engine._copy_layout import (
    _copy_lab,
    _daedalus_dir,
    _data_paths,
    _manifest_dirs,
    _run,
    _run_once_dirs,
)

pytestmark = pytest.mark.integration


# An inline stdlib lab in the demo shape: gen (emitter) -> prep (brancher) ->
# {m_a, m_b} -> merge (walk_collector) -> report (flight_collector).
# m_a sorts before m_b, so walk_1 is m_a and walk_2 is m_b.

_GEN = """\
import json
import daedalus.flow as dae


@dae.entry
def gen(ctx: dae.FlowContext) -> None:
    (ctx.step_output_path / "roster.json").write_text(json.dumps({"n": 1}))
"""

_PASSTHRU = """\
import json
import daedalus.flow as dae


@dae.entry
def {name}(ctx: dae.FlowContext) -> None:
    (ctx.step_output_path / "{out}.json").write_text(json.dumps({{"step": "{name}"}}))
"""

_METHOD = """\
import json
import daedalus.flow as dae


@dae.entry
def {name}(ctx: dae.FlowContext) -> None:
    (ctx.step_output_path / "method.json").write_text(
        json.dumps({{"method": "{name}"}})
    )
"""

_MERGE = """\
import json
import daedalus.flow as dae


@dae.entry
def merge(ctx: dae.FlowContext) -> None:
    methods = sorted(
        json.loads((d / "method.json").read_text())["method"]
        for d in ctx.walk_inputs.values()
    )
    (ctx.step_output_path / "merged.json").write_text(json.dumps({"methods": methods}))
"""

_REPORT = """\
import json
import daedalus.flow as dae


@dae.entry
def report(ctx: dae.FlowContext) -> None:
    payloads = [
        json.loads((d / "merged.json").read_text())
        for d in ctx.flight_inputs.values()
    ]
    (ctx.step_output_path / "report.json").write_text(
        json.dumps({"n_flights": len(payloads)})
    )
"""


def _make_flighted_lab(tmp_path: Path) -> Path:
    """Build the inline emitter+brancher demo-shape lab; return its dir."""
    lab = tmp_path / "flighted"
    lab.mkdir()
    (lab / "input").mkdir()
    (lab / "lab.yaml").write_text(
        'name: "flighted"\n'
        "modules:\n"
        "  - id: gen\n"
        "  - id: prep\n    depends: [gen]\n"
        "  - id: m_a\n    depends: [prep]\n"
        "  - id: m_b\n    depends: [prep]\n"
        "  - id: merge\n    depends: [m_a, m_b]\n"
        "  - id: report\n    depends: [merge]\n"
    )
    modules = lab / "modules"
    _write_module(modules / "gen", _GEN, role="emitter")
    _write_module(
        modules / "prep", _PASSTHRU.format(name="prep", out="prepped"), role="transform"
    )
    _write_module(modules / "m_a", _METHOD.format(name="m_a"), role="transform")
    _write_module(modules / "m_b", _METHOD.format(name="m_b"), role="transform")
    _write_module(modules / "merge", _MERGE, role="walk_collector")
    _write_module(modules / "report", _REPORT, role="flight_collector")
    return lab


def test_flighted_lab_nested_copy_tree(tmp_path: Path) -> None:
    """Two walks under flight_1, each a full copy chain, plus flight and flow final/."""
    lab = _make_flighted_lab(tmp_path)
    _result, flow = _run(lab, "flighted")

    assert _data_paths(flow) == [
        "final/report.json",
        "flights/flight_1/final/merged.json",
        "flights/flight_1/walks/walk_1/01_gen/roster.json",
        "flights/flight_1/walks/walk_1/02_prep/prepped.json",
        "flights/flight_1/walks/walk_1/03_m_a/method.json",
        "flights/flight_1/walks/walk_1/04_merge/merged.json",
        "flights/flight_1/walks/walk_1/05_report/report.json",
        "flights/flight_1/walks/walk_2/01_gen/roster.json",
        "flights/flight_1/walks/walk_2/02_prep/prepped.json",
        "flights/flight_1/walks/walk_2/03_m_b/method.json",
        "flights/flight_1/walks/walk_2/04_merge/merged.json",
        "flights/flight_1/walks/walk_2/05_report/report.json",
    ]


def test_flighted_natives_carry_manifest_copies_do_not(tmp_path: Path) -> None:
    """Only the run-once dirs in .daedalus/ carry a manifest; copies carry none."""
    lab = _make_flighted_lab(tmp_path)
    _result, flow = _run(lab, "flighted")

    # the six unique instances are authoritative in the run-once store.
    assert _run_once_dirs(lab) == [
        "w1/01_gen",
        "w1/06_report",
        "w2/02_prep",
        "w2/05_merge",
        "w3/03_m_a",
        "w4/04_m_b",
    ]
    assert _manifest_dirs(flow) == []
    # every copy under a config walk dir carries data but no manifest.
    for copy_dir in (
        "flights/flight_1/walks/walk_1/01_gen",
        "flights/flight_1/walks/walk_1/02_prep",
        "flights/flight_1/walks/walk_1/04_merge",
        "flights/flight_1/walks/walk_1/05_report",
        "flights/flight_1/walks/walk_2/01_gen",
    ):
        assert (flow / copy_dir).is_dir()
        assert not (flow / copy_dir / "dae-manifest.json").exists()


def test_run_once_step_executed_exactly_once(tmp_path: Path) -> None:
    """One manifest per run-once module in .daedalus/, however many copies exist."""
    lab = _make_flighted_lab(tmp_path)
    _run(lab, "flighted")
    store = _daedalus_dir(lab)

    for module, native in (
        ("gen", "w1/01_gen"),
        ("prep", "w2/02_prep"),
        ("merge", "w2/05_merge"),
        ("report", "w1/06_report"),
    ):
        manifests = sorted(store.rglob(f"*_{module}/dae-manifest.json"))
        assert len(manifests) == 1, (
            f"{module} ran {len(manifests)} times, expected exactly 1"
        )
        assert manifests[0].parent.relative_to(store).as_posix() == native


def test_flighted_walk_inputs_keyed_by_user_walk(tmp_path: Path) -> None:
    """merge's ctx.walk_inputs is keyed by user-facing walk_J, not internal w<id>."""
    from tests.core.engine._local_engine import _build_run_plan_for_test

    lab = _make_flighted_lab(tmp_path)
    _result, _flow = _run(lab, "flighted")
    run = _build_run_plan_for_test(lab)

    inputs = run.walk_input_dirs("merge@w2")
    assert set(inputs) == {"walk_1", "walk_2"}
    # the values are the run-once tails in .daedalus/, never the copies.
    assert inputs["walk_1"].as_posix().endswith(".daedalus/w3/03_m_a")
    assert inputs["walk_2"].as_posix().endswith(".daedalus/w4/04_m_b")


def test_copy_failure_is_non_fatal_and_leaves_no_partial(tmp_path, monkeypatch) -> None:
    """A raising os.replace leaves no partial copy dir and the run stays completed."""
    import os

    real_replace = os.replace
    calls = {"n": 0}

    def flaky_replace(src, dst):
        # Fail only the first walk-copy rename (a `.tmp` staging dir moving into a
        # walk step dir); manifest writes rename a `.json` file and pass through.
        is_walk_copy = (
            str(src).endswith(".tmp")
            and "/walks/" in str(dst)
            and not str(dst).endswith(".json")
        )
        if is_walk_copy and calls["n"] == 0:
            calls["n"] += 1
            raise OSError("injected copy failure")
        return real_replace(src, dst)

    # _instance.py does ``import os`` then ``os.replace``, so patching the shared os
    # module object intercepts the engine's copy rename (and lineage's, which the
    # path filter above lets through).
    monkeypatch.setattr(os, "replace", flaky_replace)

    plan_lab = _copy_lab("diamond_join", tmp_path)
    result, flow = _run(plan_lab, "diamond_join")
    assert result.status == "completed"
    # the run-once store is intact.
    assert (_daedalus_dir(plan_lab) / "w1" / "04_join" / "joined.json").exists()
    # no half-written staging dir survives anywhere (flow tree nor run-once store).
    assert not any(flow.rglob("*.tmp"))
    assert not any(_daedalus_dir(plan_lab).rglob("*.tmp"))
    assert calls["n"] == 1
    # the injected failure hit the first copy (walks/walk_1/01_seed), so that dir
    # is absent rather than empty or partial.
    assert not (flow / "walks" / "walk_1" / "01_seed").exists()
    # the failure is per copy, so every other copy still materialized.
    assert _data_paths(flow) == [
        "final/joined.json",
        "walks/walk_1/02_left/value.json",
        "walks/walk_1/03_join/joined.json",
        "walks/walk_2/01_seed/value.json",
        "walks/walk_2/02_right/value.json",
        "walks/walk_2/03_join/joined.json",
    ]


def test_rerun_byte_identical_including_copies(tmp_path: Path) -> None:
    """Two runs at the same seed write byte-identical run-once dirs and copies."""
    lab_a = _copy_lab("diamond_join", tmp_path / "a")
    lab_b = _copy_lab("diamond_join", tmp_path / "b")
    _ra, flow_a = _run(lab_a, "diamond_join")
    _rb, flow_b = _run(lab_b, "diamond_join")

    assert _data_paths(flow_a) == _data_paths(flow_b)
    assert _data_paths(flow_a), "no data files written (layout not cut over)"
    for rel in _data_paths(flow_a):
        assert (flow_a / rel).read_bytes() == (flow_b / rel).read_bytes()


def test_seeds_unchanged_under_relayout(tmp_path: Path) -> None:
    """The seed keys on the internal instance id (module@w<id>), not on walk_J."""
    from daedalus.core.engine.step import derive_seed

    lab = _copy_lab("linear_smoke", tmp_path)
    _run(lab, "linear_smoke")
    manifest = json.loads(
        (_daedalus_dir(lab) / "w2" / "02_debug_io" / "dae-manifest.json").read_text()
    )
    assert manifest["seed"] == derive_seed(0, "debug_io@w2")
    assert manifest["instance_id"] == "debug_io@w2"
    assert manifest["walk_id"] == "w2"
    # the seed key is the full instance id, not the bare module or the walk token
    # (a relayout that moved the key onto either draws a different seed).
    assert manifest["seed"] != derive_seed(0, "debug_io")
    assert manifest["seed"] != derive_seed(0, "w2")


def test_lineage_v3_user_walk_on_branch_records(tmp_path: Path) -> None:
    """Branch walks carry user_walk and the root walk keeps null; timing makes it v4."""
    plan_lab = _copy_lab("diamond_join", tmp_path)
    _result, flow = _run(plan_lab, "diamond_join")
    record = json.loads((flow / "dae-flow.json").read_text())
    assert record["format_version"] == 4
    walks = {w["walk_id"]: w for w in record["walks"]}
    assert walks["w1"].get("user_walk") is None
    assert walks["w2"]["user_walk"] == "walk_1"
    assert walks["w3"]["user_walk"] == "walk_2"


def test_each_run_has_a_distinct_input_lineage(tmp_path: Path) -> None:
    """Distinct input lineages per module equal the planned instance count."""
    from collections import Counter, defaultdict

    from daedalus.core import walks as walk_model
    from daedalus.core.recipe import load_recipe

    # The generic fixture (tests/fixtures/labs/complex), not the shipped example:
    # the assertions below name module_V and module_S, ids only the fixture has.
    lab = _copy_lab("complex", tmp_path)
    _result, flow = _run(lab, "complex")

    plan = walk_model.propagate(load_recipe(lab / "lab.yaml"), lab)
    assert isinstance(
        plan, walk_model.WalkPlan
    )  # complex is valid; narrow off WalkDefect
    predicted = Counter(inst.module_id for inst in plan.instances)

    lineages_of: dict[str, set[str]] = defaultdict(set)
    for marker in flow.rglob("marker.json"):
        record = json.loads(marker.read_text())
        lineages_of[record["module"]].add(record["path"])
    actual = {module: len(paths) for module, paths in lineages_of.items()}

    # per module, distinct input lineages equal the predicted run count.
    assert actual == dict(predicted)
    # one distinct input lineage per planned run, across the whole lab.
    every_lineage = {path for paths in lineages_of.values() for path in paths}
    assert len(every_lineage) == len(plan.instances)
    # the two discriminating cases, named so a regression is legible at a glance.
    assert actual["module_V"] == 2  # reached via module_T and via module_U
    assert actual["module_S"] == 1  # after the region-1 collector: one input
