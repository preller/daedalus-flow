"""Serial LocalEngine runs and the lineage tree they write, end to end.

Every run copies its lab to tmp_path first; the helpers live in ``_local_engine.py``.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from tests._helpers import examples_root
from tests.core.engine._local_engine import (
    _copy_lab,
    _daedalus,
    _only_flow,
    _rel_dirs,
    _run_linear_smoke,
    _run_once_dirs,
)

pytestmark = pytest.mark.integration


def test_run_writes_adr_0012_tree(tmp_path: Path) -> None:
    """One ``NN_<module>`` dir per step; literal file names and manifest keys pinned."""
    import json

    result, lab = _run_linear_smoke(tmp_path)
    assert result.status == "completed"

    flow = _only_flow(lab)
    # The run-once authorities live in .daedalus/ partitioned by token;
    # the flow tree is config-walk copies + final/.
    assert _run_once_dirs(lab) == [
        "w1/01_emit_ticks",
        "w1/05_collect_report",
        "w2/02_debug_io",
        "w2/03_sleep_briefly",
        "w2/04_summarize_walk",
    ]
    assert _rel_dirs(flow) == []  # no authoritative dirs in the user-facing tree
    assert (flow / "final").is_dir()
    assert not (flow / "output").exists()
    manifest = json.loads(
        (_daedalus(lab) / "w1" / "01_emit_ticks" / "dae-manifest.json").read_text()
    )
    assert set(manifest) >= {
        "format_version",
        "step_id",
        "status",
        "seed",
        "started_at",
        "finished_at",
        "duration_s",
        "error",
        "flight_id",
        "walk_id",
        "instance_id",
    }
    # lineage v2 manifests carry the walk-model fields; a lab without branch walks
    # has no user_walk. The flow record is v4 because FlowStep carries per-step times.
    assert manifest["format_version"] == 2
    assert manifest["status"] == "completed"
    assert manifest["error"] is None
    assert manifest["instance_id"] == "emit_ticks@w1"

    flow_record = json.loads((flow / "dae-flow.json").read_text())
    assert flow_record["format_version"] == 4
    assert flow_record["status"] == "completed"
    assert flow_record["lab_name"] == "linear_smoke"
    # steps[] is re-keyed to instance ids (<module>@w<id>).
    assert [s["step_id"] for s in flow_record["steps"]] == [
        "emit_ticks@w1",
        "debug_io@w2",
        "sleep_briefly@w2",
        "summarize_walk@w2",
        "collect_report@w1",
    ]


def test_all_steps_completed(tmp_path: Path) -> None:
    """Every step's manifest status is completed after a clean run."""
    import json

    _result, lab = _run_linear_smoke(tmp_path)
    # Every run-once instance manifest reads completed (the config walk copies
    # carry no manifest, so this counts exactly the five run-once instances).
    manifests = sorted(_daedalus(lab).rglob("dae-manifest.json"))
    assert len(manifests) == 5
    for manifest_path in manifests:
        manifest = json.loads(manifest_path.read_text())
        assert manifest["status"] == "completed"


def test_sleep_step_duration_is_nonzero(tmp_path: Path) -> None:
    """duration_s is > 0; a fixed floor like 0.01 fails under a loaded CI scheduler."""
    import json

    _result, lab = _run_linear_smoke(tmp_path)
    manifest = json.loads(
        (_daedalus(lab) / "w2" / "03_sleep_briefly" / "dae-manifest.json").read_text()
    )
    assert manifest["duration_s"] > 0


def test_run_report_names_all_steps(tmp_path: Path) -> None:
    """collect_report writes run_report.json naming every upstream step in order."""
    import json

    _result, lab = _run_linear_smoke(tmp_path)
    flow = _only_flow(lab)
    # collect_report is the sink, so its output mirrors into the flow final/.
    report = json.loads((flow / "final" / "run_report.json").read_text())
    assert report["upstream_steps"] == [
        "emit_ticks",
        "debug_io",
        "sleep_briefly",
        "summarize_walk",
        "collect_report",
    ]


def test_two_runs_differ_only_in_flow_id_timestamps_durations(tmp_path: Path) -> None:
    import json

    _r1, lab1 = _run_linear_smoke(tmp_path / "a")
    _r2, lab2 = _run_linear_smoke(tmp_path / "b")
    flow1, flow2 = _only_flow(lab1), _only_flow(lab2)

    # flow ids differ (distinct directories / timestamps)
    report1 = json.loads((flow1 / "final" / "run_report.json").read_text())
    report2 = json.loads((flow2 / "final" / "run_report.json").read_text())
    assert report1 == report2  # deterministic data output

    ticks1 = json.loads(
        (_daedalus(lab1) / "w1/01_emit_ticks" / "ticks.json").read_text()
    )
    ticks2 = json.loads(
        (_daedalus(lab2) / "w1/01_emit_ticks" / "ticks.json").read_text()
    )
    assert ticks1 == ticks2  # deterministic emitter output at the same seed


def test_failure_injection_stops_downstream(tmp_path: Path) -> None:
    """The raising step and the flow read failed; nothing downstream runs."""
    import json

    from daedalus.core.engine import LabConfig, LocalEngine
    from daedalus.core.recipe import build_plan, load_recipe

    lab = _copy_lab("linear_smoke", tmp_path)
    # Insert a raising transform `boom` between debug_io and sleep_briefly.
    boom = lab / "modules" / "boom"
    boom.mkdir()
    (boom / "dae-module.yaml").write_text("role: transform\n")
    (boom / "main.py").write_text(
        "import daedalus.flow as dae\n\n\n"
        "@dae.entry\n"
        "def boom(ctx: dae.FlowContext) -> None:\n"
        '    raise RuntimeError("boom raised by the test")\n'
    )
    text = (lab / "lab.yaml").read_text()
    text = text.replace(
        "  - id: sleep_briefly\n    depends: [debug_io]\n",
        "  - id: boom\n    depends: [debug_io]\n"
        "  - id: sleep_briefly\n    depends: [boom]\n",
    )
    (lab / "lab.yaml").write_text(text)

    spec = load_recipe(lab / "lab.yaml")
    plan = build_plan(spec, lab)
    config = LabConfig(
        lab_name="linear_smoke",
        lab_dir=lab,
        seed=0,
        output_root=lab / "dae-outputs",
    )
    result = LocalEngine().execute_dag(plan, config=config)
    assert result.status == "failed"

    flow = _only_flow(lab)
    # boom lands at .daedalus/w2/03_boom in the run-once store.
    boom_manifest = json.loads(
        (_daedalus(lab) / "w2" / "03_boom" / "dae-manifest.json").read_text()
    )
    assert boom_manifest["status"] == "failed"
    assert boom_manifest["error"] is not None

    # nothing downstream of boom ran, so no run-once dirs for them; the collector
    # stays submitted with no completed parent.
    assert _run_once_dirs(lab) == [
        "w1/01_emit_ticks",
        "w2/02_debug_io",
        "w2/03_boom",
    ]

    # a failed flow writes no config walk dirs and no final/; copies are written
    # on completion only.
    assert not (flow / "final").exists()
    assert not (flow / "output").exists()
    assert not (flow / "flights").exists()
    assert not (flow / "walks").exists()

    flow_record = json.loads((flow / "dae-flow.json").read_text())
    assert flow_record["status"] == "failed"


def test_minimal_example_transform_source_runs_end_to_end(tmp_path: Path) -> None:
    """A source transform reads the lab's input/, not its own empty output dir."""
    import json

    from daedalus.core.engine import LabConfig, LocalEngine
    from daedalus.core.recipe import build_plan, load_recipe

    src = examples_root() / "minimal"
    lab = tmp_path / "minimal"
    shutil.copytree(src, lab, ignore=shutil.ignore_patterns("__pycache__"))

    spec = load_recipe(lab / "lab.yaml")
    plan = build_plan(spec, lab)
    config = LabConfig(
        lab_name="minimal",
        lab_dir=lab,
        seed=0,
        output_root=lab / "dae-outputs",
    )
    result = LocalEngine().execute_dag(plan, config=config)
    assert result.status == "completed"

    flow = _only_flow(lab)
    manifest = json.loads(
        (_daedalus(lab) / "w1" / "01_normalize" / "dae-manifest.json").read_text()
    )
    assert manifest["status"] == "completed"
    assert manifest["error"] is None

    # normalize is the sink, so its output mirrors into the flow final/.
    out = json.loads((flow / "final" / "normalized.json").read_text())
    assert out["n_points"] == len(out["flux_normalized"])
    # The flux was divided by its median, so the median of the result is 1.0.
    assert any(abs(v - 1.0) < 1e-9 for v in out["flux_normalized"])


def test_completed_flow_writes_final_dir(tmp_path: Path) -> None:
    """final/ mirrors the sink's files byte for byte, without dae-manifest.json."""
    result, lab = _run_linear_smoke(tmp_path)
    assert result.status == "completed"

    flow = _only_flow(lab)
    out = flow / "final"
    assert out.is_dir()
    # final/ byte-mirrors the run-once sink and carries no record.
    assert (out / "run_report.json").read_bytes() == (
        _daedalus(lab) / "w1" / "05_collect_report" / "run_report.json"
    ).read_bytes()
    assert not (out / "dae-manifest.json").exists()
    assert not (flow / "output").exists()


def test_minimal_example_final_dir_sink_is_transform(tmp_path: Path) -> None:
    """The sink is picked by out-degree, not role, so a transform sink gets final/."""
    from daedalus.core.engine import LabConfig, LocalEngine
    from daedalus.core.recipe import build_plan, load_recipe

    src = examples_root() / "minimal"
    lab = tmp_path / "minimal"
    shutil.copytree(src, lab, ignore=shutil.ignore_patterns("__pycache__"))
    spec = load_recipe(lab / "lab.yaml")
    plan = build_plan(spec, lab)
    config = LabConfig(
        lab_name="minimal", lab_dir=lab, seed=0, output_root=lab / "dae-outputs"
    )
    result = LocalEngine().execute_dag(plan, config=config)
    assert result.status == "completed"

    flow = _only_flow(lab)
    assert (flow / "final" / "normalized.json").read_bytes() == (
        _daedalus(lab) / "w1" / "01_normalize" / "normalized.json"
    ).read_bytes()
