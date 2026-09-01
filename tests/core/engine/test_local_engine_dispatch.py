"""Nested-walk, instance-keyed dispatch of the LocalEngine, end to end.

Helpers live in ``_local_engine.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests._helpers import chdir
from tests.core.engine._local_engine import (
    _copy_diamond_join,
    _copy_lab,
    _daedalus,
    _only_flow,
    _rel_dirs,
    _run_linear_smoke,
    _run_once_dirs,
)

pytestmark = pytest.mark.integration


def test_linear_smoke_tree_is_single_configuration_layout(tmp_path: Path) -> None:
    """One chain under flights/flight_1/walks/walk_1/, run-once dirs in .daedalus/."""
    _result, lab = _run_linear_smoke(tmp_path)
    flow = _only_flow(lab)
    # the run-once authorities live in .daedalus/; the flow tree is copies-only.
    assert _run_once_dirs(lab) == [
        "w1/01_emit_ticks",
        "w1/05_collect_report",
        "w2/02_debug_io",
        "w2/03_sleep_briefly",
        "w2/04_summarize_walk",
    ]
    assert _rel_dirs(flow) == []
    assert sorted(
        p.relative_to(flow).as_posix()
        for p in (flow / "flights").rglob("*")
        if p.is_dir()
    ) == [
        "flights/flight_1",
        "flights/flight_1/final",
        "flights/flight_1/walks",
        "flights/flight_1/walks/walk_1",
        "flights/flight_1/walks/walk_1/01_emit_ticks",
        "flights/flight_1/walks/walk_1/02_debug_io",
        "flights/flight_1/walks/walk_1/03_sleep_briefly",
        "flights/flight_1/walks/walk_1/04_summarize_walk",
        "flights/flight_1/walks/walk_1/05_collect_report",
    ]
    # The sink (collect_report) mirrors into final/.
    out = flow / "final"
    assert out.is_dir()
    assert (out / "run_report.json").exists()
    assert not (flow / "output").exists()


def test_diamond_join_runs_end_to_end_engine_level(tmp_path: Path) -> None:
    """Owns the lineage shape only; the join value is pinned in test_copy_layout."""
    from daedalus.core.engine import LocalEngine

    plan, config, lab = _copy_diamond_join(tmp_path)
    result = LocalEngine().execute_dag(plan, config=config)
    assert result.status == "completed", result.error

    flow = _only_flow(lab)
    # the run-once dirs live in .daedalus/ and copies carry no manifest: seed and
    # join on w1, the two methods on w2 and w3.
    assert _run_once_dirs(lab) == [
        "w1/01_seed",
        "w1/04_join",
        "w2/02_left",
        "w3/03_right",
    ]
    assert _rel_dirs(flow) == []
    # the sink mirrors the join into final/; only the mirror's existence and the
    # absence of output/ are checked here.
    assert (flow / "final" / "joined.json").exists()
    assert not (flow / "output").exists()


def test_lineage_v2_instance_keyed(tmp_path: Path) -> None:
    """The flow record is v4 with instance-keyed steps and walks; manifests are v2."""
    import json

    _result, lab = _run_linear_smoke(tmp_path)
    flow = _only_flow(lab)

    record = json.loads((flow / "dae-flow.json").read_text())
    assert record["format_version"] == 4
    assert [s["step_id"] for s in record["steps"]] == [
        "emit_ticks@w1",
        "debug_io@w2",
        "sleep_briefly@w2",
        "summarize_walk@w2",
        "collect_report@w1",
    ]
    walks = {w["walk_id"]: w for w in record["walks"]}
    assert set(walks) == {"w1", "w2"}
    assert walks["w1"]["flight_id"] is None
    assert walks["w1"]["parent_walk"] is None
    assert walks["w2"]["flight_id"] == "f1"
    assert walks["w2"]["parent_walk"] == "w1"
    assert walks["w2"]["born_at"] == "emit_ticks"

    manifest = json.loads(
        (_daedalus(lab) / "w2" / "02_debug_io" / "dae-manifest.json").read_text()
    )
    assert manifest["format_version"] == 2
    assert manifest["instance_id"] == "debug_io@w2"
    assert manifest["walk_id"] == "w2"
    assert manifest["flight_id"] == "f1"
    assert manifest["step_id"] == "debug_io"


def test_module_status_is_instance_keyed(tmp_path: Path) -> None:
    """ExecutionResult.module_status is keyed by instance id."""
    result, _lab = _run_linear_smoke(tmp_path)
    assert set(result.module_status) == {
        "emit_ticks@w1",
        "debug_io@w2",
        "sleep_briefly@w2",
        "summarize_walk@w2",
        "collect_report@w1",
    }
    assert all(status == "completed" for status in result.module_status.values())


def test_seeds_key_on_instance_id_end_to_end(tmp_path: Path) -> None:
    """debug_io sees seed derive_seed(0, 'debug_io@w2') and walk_id 'w2'."""
    import json

    from daedalus.core.engine.step import derive_seed

    _result, lab = _run_linear_smoke(tmp_path)
    debug_io = _daedalus(lab) / "w2" / "02_debug_io"
    seen = json.loads((debug_io / "ticks.json").read_text())["seen"]
    assert seen["walk_id"] == "w2"
    assert seen["seed"] == derive_seed(0, "debug_io@w2")
    # the manifest seed agrees with the in-module observed seed
    manifest = json.loads((debug_io / "dae-manifest.json").read_text())
    assert manifest["seed"] == derive_seed(0, "debug_io@w2")
    # the key is the full instance id, not the bare module or the walk token;
    # re-keying onto either draws a different value.
    assert seen["seed"] != derive_seed(0, "debug_io")
    assert seen["seed"] != derive_seed(0, "w2")


def test_finalize_outputs_writes_flow_final_only_on_completed(tmp_path: Path) -> None:
    """final/ mirrors the sink minus dae-* files, and only on a completed flow."""
    import json

    from daedalus.core.engine.local import _finalize_outputs
    from daedalus.core.walks import Instance, WalkPlan

    def _plan(terminal: tuple[str, ...], instances: tuple[Instance, ...]) -> WalkPlan:
        return WalkPlan(
            walks=(),
            instances=instances,
            edges=(),
            walk_inputs={},
            terminal=terminal,
            roles={},
            config_full="",
            _lines=(),
        )

    def _make_run(flow: Path, plan: WalkPlan, dir_of: dict[str, Path]):
        from daedalus.core.engine.local import _RunPlan
        from daedalus.core.engine.protocol import LabConfig

        return _RunPlan(
            flow_dir=flow,
            daedalus_root=flow / ".daedalus",
            config=LabConfig(lab_name="x", lab_dir=flow, seed=0, output_root=flow),
            walk_plan=plan,
            dir_of=dir_of,
            parents_of={},
            record_of={},
            user_walk_of={},
            has_flights=False,
            module_dir_of={},
            role_of={},
        )

    sink = tmp_path / "flow" / "04_sink"
    sink.mkdir(parents=True)
    (sink / "out.json").write_text(json.dumps({"m": "sink"}))
    (sink / "dae-manifest.json").write_text(json.dumps({"format_version": 1}))
    plan = _plan(("sink@w1",), (Instance("sink@w1", "sink", "w1", 4),))
    run = _make_run(tmp_path / "flow", plan, {"sink@w1": sink})

    # not completed -> no final/.
    _finalize_outputs(run, "failed")
    assert not (tmp_path / "flow" / "final").exists()

    # completed -> final/ mirrors the sink, excluding dae-*.
    _finalize_outputs(run, "completed")
    assert (tmp_path / "flow" / "final" / "out.json").exists()
    assert not (tmp_path / "flow" / "final" / "dae-manifest.json").exists()
    assert not (tmp_path / "flow" / "output").exists()


def test_rerun_uses_fresh_flow_id_dirs_disjoint(tmp_path: Path) -> None:
    """Two runs at the same seed write byte-identical data in distinct flow dirs."""
    _r1, lab1 = _run_linear_smoke(tmp_path / "a")
    _r2, lab2 = _run_linear_smoke(tmp_path / "b")

    # the run-once store reproduces byte-for-byte at the same seed (the copies are
    # pure mirrors over it, so the whole tree follows).
    assert _run_once_dirs(lab1) == _run_once_dirs(lab2)
    assert _run_once_dirs(lab1), "no run-once dirs written (layout not cut over)"
    for rel in _run_once_dirs(lab1):
        for data in sorted((_daedalus(lab1) / rel).glob("*.json")):
            if data.name == "dae-manifest.json":
                continue
            assert data.read_bytes() == (_daedalus(lab2) / rel / data.name).read_bytes()


def test_get_status_reads_back_real_lineage(tmp_path: Path) -> None:
    """get_status reads the on-disk lineage back into a FlowStatus."""
    from daedalus.core.engine import LabConfig, LocalEngine
    from daedalus.core.recipe import build_plan, load_recipe

    lab = _copy_lab("linear_smoke", tmp_path)
    spec = load_recipe(lab / "lab.yaml")
    plan = build_plan(spec, lab)
    config = LabConfig(
        lab_name="linear_smoke",
        lab_dir=lab,
        seed=0,
        output_root=lab / "dae-outputs",
    )
    engine = LocalEngine()
    result = engine.execute_dag(plan, config=config)

    # get_status resolves dae-outputs/ from cwd; run from inside the lab copy so
    # the read-back targets the lineage that was just written.
    with chdir(lab):
        status = engine.get_status(result.flow_id)
    assert status.flow_id == result.flow_id
    assert status.status == "completed"
    assert status.lab_name == "linear_smoke"
    # module_status is instance-keyed (golden bump): read back from the v2
    # instance-keyed steps[].
    assert set(status.module_status) == {
        "emit_ticks@w1",
        "debug_io@w2",
        "sleep_briefly@w2",
        "summarize_walk@w2",
        "collect_report@w1",
    }
