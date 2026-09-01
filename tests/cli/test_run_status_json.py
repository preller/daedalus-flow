"""``--json`` payload of ``lab run`` and ``flow status``: engine info and failure cause.

Both commands render from ``render.flow_status_payload``; every enrichment is additive.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from daedalus.cli.app import app
from daedalus.cli.render import failure_cause, flow_status_payload
from daedalus.core import lineage
from tests._helpers import chdir
from tests.cli._cli_contract import (
    _copy_fixture_lab,
    _only_flow,
    _reset_json_state,
)

pytestmark = pytest.mark.integration

# Re-export the autouse fixture so ruff does not flag it; pytest resolves by name.
__all__ = ["_reset_json_state"]


def _run_json(lab_dir: Path, *args: str) -> dict:
    """Invoke ``dae --json <args>`` in ``lab_dir`` and return the parsed payload."""
    runner = CliRunner()
    with chdir(lab_dir):
        result = runner.invoke(app, ["--json", *args], prog_name="dae")
    return json.loads(result.stdout)


# engine and max_workers on the machine surface, run and status


def test_run_json_payload_names_engine_and_max_workers(tmp_path: Path) -> None:
    """`lab run --json` carries ``engine`` and ``max_workers`` (the default lab)."""
    lab = _copy_fixture_lab("linear_smoke", tmp_path)
    payload = _run_json(lab, "lab", "run")

    assert payload["code"] == "dae.lab.run.ok"
    assert payload["exit"] == 0
    # A successful run carries an always-present, null envelope error.
    assert payload["error"] is None
    # A serial run is observable as such (under the ``data`` nest).
    assert payload["data"]["engine"] == "local"
    assert payload["data"]["max_workers"] == 1


def test_status_json_payload_names_engine_and_max_workers(tmp_path: Path) -> None:
    """Status reads only the on-disk record, so the engine info is in the lineage."""
    lab = _copy_fixture_lab("linear_smoke", tmp_path)
    run = _run_json(lab, "lab", "run")
    assert run["code"] == "dae.lab.run.ok"

    payload = _run_json(lab, "flow", "status")
    assert payload["code"] == "dae.flow.status.ok"
    assert payload["data"]["engine"] == "local"
    assert payload["data"]["max_workers"] == 1


def test_run_json_payload_keeps_existing_keys(tmp_path: Path) -> None:
    """The prior payload keys are all still present after the enrichment."""
    lab = _copy_fixture_lab("linear_smoke", tmp_path)
    payload = _run_json(lab, "lab", "run")

    for key in ("code", "exit"):
        assert key in payload, f"lost envelope key {key!r}"
    for key in ("flow_id", "lab_name", "status", "created_at", "steps"):
        assert key in payload["data"], f"lost payload key {key!r}"
    assert payload["data"]["status"] == "completed"
    assert isinstance(payload["data"]["steps"], list)
    # The new keys never displace the step shape.
    for step in payload["data"]["steps"]:
        assert {"id", "status", "duration_s"} <= step.keys()


# the builder reads the degree off the record


def test_flow_status_payload_reflects_record_engine_and_workers() -> None:
    """A record for a parallel Prefect run reports its degree, not local and 1."""
    record = lineage.FlowRecord(
        flow_id="flow_20260618_120000",
        lab_name="parallel_lab",
        status="completed",
        created_at="2026-06-18T12:00:00+00:00",
        steps=(lineage.FlowStep(step_id="emit@w1", status="completed"),),
        engine="prefect",
        max_workers=4,
    )
    payload = flow_status_payload(record)
    assert payload["engine"] == "prefect"
    assert payload["max_workers"] == 4


def test_flow_record_engine_workers_round_trip_and_default_bytes(
    tmp_path: Path,
) -> None:
    """The keys serialize only off the default, so a default record stays v1."""
    default_record = lineage.FlowRecord(
        flow_id="flow_20260618_120000",
        lab_name="linear_smoke",
        status="completed",
        created_at="2026-06-18T12:00:00+00:00",
        steps=(lineage.FlowStep(step_id="emit_ticks", status="completed"),),
    )
    lineage.write_flow_record(tmp_path, default_record)
    on_disk = json.loads((tmp_path / lineage.FLOW_RECORD_NAME).read_text())
    assert on_disk["format_version"] == 1
    assert "engine" not in on_disk
    assert "max_workers" not in on_disk
    assert lineage.read_flow_record(tmp_path) == default_record

    parallel = lineage.FlowRecord(
        flow_id="flow_20260618_130000",
        lab_name="parallel_lab",
        status="completed",
        created_at="2026-06-18T13:00:00+00:00",
        steps=(lineage.FlowStep(step_id="emit@w1", status="completed"),),
        engine="prefect",
        max_workers=4,
    )
    lineage.write_flow_record(tmp_path, parallel)
    back = lineage.read_flow_record(tmp_path)
    assert back.engine == "prefect"
    assert back.max_workers == 4


# a failure names its cause, durably


def test_failure_cause_surfaces_from_failed_step() -> None:
    """The cause is the envelope ``error`` object, not a key inside ``data``."""
    record = lineage.FlowRecord(
        flow_id="flow_20260618_140000",
        lab_name="flight_one_fails",
        status="failed",
        created_at="2026-06-18T14:00:00+00:00",
        steps=(
            lineage.FlowStep(step_id="emit@w1", status="completed"),
            lineage.FlowStep(
                step_id="work@w2",
                status="failed",
                error="step 'work' raised ValueError: doomed item 20",
            ),
        ),
    )
    cause = failure_cause(record)
    assert cause is not None
    assert cause["error"] == "step 'work' raised ValueError: doomed item 20"
    assert cause["reason"] == cause["error"]
    # The run payload carries no failure keys.
    data = flow_status_payload(record)
    assert "error" not in data
    assert "reason" not in data
    # The failed step still carries its own cause (per-step durable surface).
    failed = next(s for s in data["steps"] if s["status"] == "failed")
    assert failed["error"] == "step 'work' raised ValueError: doomed item 20"


def test_failure_cause_names_missing_dep() -> None:
    """The cause recovers the top-level package from ``No module named 'X'``."""
    record = lineage.FlowRecord(
        flow_id="flow_20260618_180000",
        lab_name="needs_numpy",
        status="failed",
        created_at="2026-06-18T18:00:00+00:00",
        steps=(
            lineage.FlowStep(
                step_id="fit@w1",
                status="failed",
                error="step 'fit' failed to import: No module named 'numpy.linalg'",
            ),
        ),
    )
    cause = failure_cause(record)
    assert cause is not None
    assert cause["missing_dep"] == "numpy"
    assert cause["error"].endswith("No module named 'numpy.linalg'")


def test_failure_cause_is_none_when_completed() -> None:
    """A completed run has no cause, and ``data`` carries no failure keys."""
    record = lineage.FlowRecord(
        flow_id="flow_20260618_150000",
        lab_name="linear_smoke",
        status="completed",
        created_at="2026-06-18T15:00:00+00:00",
        steps=(lineage.FlowStep(step_id="emit_ticks", status="completed"),),
    )
    assert failure_cause(record) is None
    data = flow_status_payload(record)
    assert "error" not in data
    assert "reason" not in data
    assert "missing_dep" not in data


def test_flow_step_error_round_trips_and_default_stays_v1(tmp_path: Path) -> None:
    """A FlowStep ``error`` is durable; an error-less record keeps version-1 bytes."""
    failed_record = lineage.FlowRecord(
        flow_id="flow_20260618_160000",
        lab_name="flight_one_fails",
        status="failed",
        created_at="2026-06-18T16:00:00+00:00",
        steps=(
            lineage.FlowStep(
                step_id="work@w2",
                status="failed",
                error="boom",
            ),
        ),
    )
    lineage.write_flow_record(tmp_path, failed_record)
    on_disk = json.loads((tmp_path / lineage.FLOW_RECORD_NAME).read_text())
    failed_step = next(s for s in on_disk["steps"] if s["status"] == "failed")
    assert failed_step["error"] == "boom"
    assert lineage.read_flow_record(tmp_path) == failed_record

    # An error-less step must not gain the key (byte stability of the v1 goldens).
    clean_record = lineage.FlowRecord(
        flow_id="flow_20260618_170000",
        lab_name="linear_smoke",
        status="completed",
        created_at="2026-06-18T17:00:00+00:00",
        steps=(lineage.FlowStep(step_id="emit_ticks", status="completed"),),
    )
    lineage.write_flow_record(tmp_path, clean_record)
    clean_disk = json.loads((tmp_path / lineage.FLOW_RECORD_NAME).read_text())
    assert "error" not in clean_disk["steps"][0]
    assert clean_disk["format_version"] == 1


def test_error_code_round_trips_on_manifest_and_flow_step(tmp_path: Path) -> None:
    """``error_code`` rides next to ``error`` on the step manifest and the flow step."""
    manifest = lineage.StepManifest(
        step_id="work@w2",
        status="failed",
        seed=7,
        error="step work@w2 raised ValueError: boom",
        error_code="dae.step.execution_failed",
        flight_id="f2",
        walk_id="w2",
        instance_id="work@w2",
    )
    lineage.write_step_manifest(tmp_path, manifest)
    assert lineage.read_step_manifest(tmp_path) == manifest
    on_disk = json.loads((tmp_path / lineage.STEP_MANIFEST_NAME).read_text())
    assert on_disk["error_code"] == "dae.step.execution_failed"

    record = lineage.FlowRecord(
        flow_id="flow_20260625_120000",
        lab_name="flight_one_fails",
        status="failed",
        created_at="2026-06-25T12:00:00+00:00",
        steps=(
            lineage.FlowStep(
                step_id="work@w2",
                status="failed",
                error="step work@w2 raised ValueError: boom",
                error_code="dae.step.execution_failed",
            ),
        ),
    )
    lineage.write_flow_record(tmp_path, record)
    assert lineage.read_flow_record(tmp_path) == record
    flow_disk = json.loads((tmp_path / lineage.FLOW_RECORD_NAME).read_text())
    failed_step = next(s for s in flow_disk["steps"] if s["status"] == "failed")
    assert failed_step["error_code"] == "dae.step.execution_failed"


def test_error_code_absent_keeps_prior_bytes_and_legacy_reads(tmp_path: Path) -> None:
    """An error-code-less record omits the key; a legacy record without it reads."""
    clean = lineage.StepManifest(step_id="emit_ticks", status="completed", seed=1)
    lineage.write_step_manifest(tmp_path, clean)
    clean_disk = json.loads((tmp_path / lineage.STEP_MANIFEST_NAME).read_text())
    assert "error_code" not in clean_disk

    # A pre-existing manifest written before this field still reads (tolerance):
    # error_code resolves to None, the rest unchanged.
    legacy = dict(clean_disk)
    legacy.pop("error_code", None)
    (tmp_path / lineage.STEP_MANIFEST_NAME).write_text(json.dumps(legacy))
    assert lineage.read_step_manifest(tmp_path).error_code is None


def test_real_failing_run_records_cause_in_step_manifest(tmp_path: Path) -> None:
    """The serial engine over flight_one_fails writes the cause to a step manifest."""
    lab = _copy_fixture_lab("flight_one_fails", tmp_path)
    run = _run_json(lab, "lab", "run")
    assert run["code"] == "dae.lab.run.failed"
    assert run["exit"] == 1

    record = lineage.read_flow_record(_only_flow(lab))
    assert record.status == "failed"

    # The per-step manifests live in the run-once store under the lab cwd
    # (``.daedalus/<walk>/<NN>_<module>/``), the durable per-step lineage.
    manifests = [
        lineage.read_step_manifest(p.parent)
        for p in lab.rglob(lineage.STEP_MANIFEST_NAME)
    ]
    failed = [m for m in manifests if m.status == "failed"]
    assert failed, "expected at least one failed step manifest"
    assert any(m.error for m in failed), "failed step manifest must carry its cause"

    # The flow record's failed step carries the cause too, and the run --json
    # envelope surfaces it with the engine degree, so a reader never has to
    # open the manifests.
    failed_steps = [s for s in record.steps if s.status == "failed"]
    assert failed_steps, "expected at least one failed step in the flow record"
    assert any(s.error for s in failed_steps), "flow record must carry the cause"
    assert run["error"], "run --json must name the failure cause in the envelope"
    assert run["error"]["error"], "envelope error must carry the cause message"
    assert run["error"]["reason"], "envelope error must carry the failure reason"
    # The cause lives in the envelope error slot alone, never inside data.
    assert "error" not in run["data"]
    assert run["data"]["engine"] == "local"
    assert run["data"]["max_workers"] == 1
