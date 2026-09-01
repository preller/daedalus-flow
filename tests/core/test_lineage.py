"""Schema and round-trip tests for the lineage record across format versions.

Stdlib-only JSON, all writes to tmp_path; the IO half is in test_lineage_io.py.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from daedalus.core import lineage

if TYPE_CHECKING:
    from pathlib import Path


def test_step_manifest_round_trips(tmp_path: Path) -> None:
    """A written manifest reads back equal, with format_version 1 on disk."""
    manifest = lineage.StepManifest(
        step_id="emit_ticks",
        status="completed",
        seed=12345,
        started_at="2026-06-11T07:32:00+00:00",
        finished_at="2026-06-11T07:32:00.500000+00:00",
        duration_s=0.5,
        error=None,
    )
    lineage.write_step_manifest(tmp_path, manifest)

    on_disk = json.loads((tmp_path / lineage.STEP_MANIFEST_NAME).read_text())
    assert on_disk["format_version"] == 1
    assert on_disk["step_id"] == "emit_ticks"
    assert on_disk["seed"] == 12345

    assert lineage.read_step_manifest(tmp_path) == manifest


def test_flow_record_round_trips(tmp_path: Path) -> None:
    """A written flow record reads back equal, steps in order."""
    record = lineage.FlowRecord(
        flow_id="flow_20260611_073200",
        lab_name="linear_smoke",
        status="completed",
        created_at="2026-06-11T07:32:00+00:00",
        steps=(
            lineage.FlowStep(step_id="emit_ticks", status="completed", duration_s=0.01),
            lineage.FlowStep(step_id="debug_io", status="completed", duration_s=0.02),
        ),
    )
    lineage.write_flow_record(tmp_path, record)

    on_disk = json.loads((tmp_path / lineage.FLOW_RECORD_NAME).read_text())
    assert on_disk["format_version"] == 1
    assert on_disk["lab_name"] == "linear_smoke"
    assert [s["step_id"] for s in on_disk["steps"]] == ["emit_ticks", "debug_io"]
    assert on_disk["daedalus_version"]  # the package version is recorded, non-empty

    assert lineage.read_flow_record(tmp_path) == record


def test_v1_records_stay_format_version_1_on_disk(tmp_path: Path) -> None:
    """Without walk-model fields the record stays version 1; the v1 goldens hold."""
    manifest = lineage.StepManifest(step_id="emit_ticks", status="completed", seed=7)
    lineage.write_step_manifest(tmp_path, manifest)
    on_manifest = json.loads((tmp_path / lineage.STEP_MANIFEST_NAME).read_text())
    assert on_manifest["format_version"] == 1
    assert "instance_id" not in on_manifest

    record = lineage.FlowRecord(
        flow_id="flow_20260611_073200",
        lab_name="linear_smoke",
        status="completed",
        created_at="2026-06-11T07:32:00+00:00",
        steps=(lineage.FlowStep(step_id="emit_ticks", status="completed"),),
    )
    lineage.write_flow_record(tmp_path, record)
    on_flow = json.loads((tmp_path / lineage.FLOW_RECORD_NAME).read_text())
    assert on_flow["format_version"] == 1
    assert "walks" not in on_flow


def test_step_manifest_v2_round_trips(tmp_path: Path) -> None:
    """A manifest carrying the additive walk fields writes/reads as version 2."""
    manifest = lineage.StepManifest(
        step_id="debug_io",
        status="completed",
        seed=42,
        flight_id="f1",
        walk_id="w2",
        instance_id="debug_io@w2",
    )
    lineage.write_step_manifest(tmp_path, manifest)

    on_disk = json.loads((tmp_path / lineage.STEP_MANIFEST_NAME).read_text())
    assert on_disk["format_version"] == 2
    assert on_disk["flight_id"] == "f1"
    assert on_disk["walk_id"] == "w2"
    assert on_disk["instance_id"] == "debug_io@w2"

    assert lineage.read_step_manifest(tmp_path) == manifest


def test_flow_record_v2_round_trips_with_walk_records(tmp_path: Path) -> None:
    """The walk five-tuple survives the round-trip, including the root's None."""
    record = lineage.FlowRecord(
        flow_id="flow_20260611_073200",
        lab_name="diamond_join",
        status="completed",
        created_at="2026-06-11T07:32:00+00:00",
        steps=(
            lineage.FlowStep(step_id="seed@w1", status="completed"),
            lineage.FlowStep(step_id="left@w2", status="completed"),
        ),
        walks=(
            lineage.WalkRecord(
                walk_id="w1",
                flight_id=None,
                parent_walk=None,
                born_at=None,
                branch_module=None,
            ),
            lineage.WalkRecord(
                walk_id="w2",
                flight_id="f1",
                parent_walk="w1",
                born_at="seed",
                branch_module="left",
            ),
        ),
    )
    lineage.write_flow_record(tmp_path, record)

    on_disk = json.loads((tmp_path / lineage.FLOW_RECORD_NAME).read_text())
    assert on_disk["format_version"] == 2
    assert [w["walk_id"] for w in on_disk["walks"]] == ["w1", "w2"]
    assert on_disk["walks"][0]["flight_id"] is None
    assert on_disk["walks"][1]["born_at"] == "seed"

    assert lineage.read_flow_record(tmp_path) == record


def test_read_accepts_format_version_2(tmp_path: Path) -> None:
    """A raw version-2 manifest is accepted on read (the reader understands 2)."""
    raw = {
        "format_version": 2,
        "step_id": "x",
        "status": "completed",
        "seed": 1,
        "flight_id": "f1",
        "walk_id": "w2",
        "instance_id": "x@w2",
    }
    (tmp_path / lineage.STEP_MANIFEST_NAME).write_text(json.dumps(raw))
    manifest = lineage.read_step_manifest(tmp_path)
    assert manifest.instance_id == "x@w2"
    assert manifest.walk_id == "w2"


def test_read_accepts_format_version_3(tmp_path: Path) -> None:
    """v3 adds user_walk; the reader accepts it, older records stay v1 or v2."""
    raw = {
        "format_version": 3,
        "step_id": "x",
        "status": "completed",
        "seed": 1,
        "flight_id": "flight_1",
        "walk_id": "w2",
        "instance_id": "x@w2",
    }
    (tmp_path / lineage.STEP_MANIFEST_NAME).write_text(json.dumps(raw))
    manifest = lineage.read_step_manifest(tmp_path)
    assert manifest.instance_id == "x@w2"
    assert manifest.walk_id == "w2"


def test_read_refuses_format_version_above_4(tmp_path: Path) -> None:
    """A version above the highest understood (4) is refused, never parsed."""
    raw = {"format_version": 5, "step_id": "x", "status": "completed", "seed": 1}
    (tmp_path / lineage.STEP_MANIFEST_NAME).write_text(json.dumps(raw))
    with pytest.raises(lineage.LineageError, match="format_version"):
        lineage.read_step_manifest(tmp_path)


def test_walk_record_with_user_walk_round_trips_at_v3(tmp_path: Path) -> None:
    """user_walk is the v3 marker and survives the round-trip beside walk_id."""
    record = lineage.FlowRecord(
        flow_id="flow_20260613_094100",
        lab_name="diamond_join",
        status="completed",
        created_at="2026-06-13T09:41:00+00:00",
        steps=(lineage.FlowStep(step_id="seed@w1", status="completed"),),
        walks=(
            lineage.WalkRecord(
                walk_id="w1",
                flight_id=None,
                parent_walk=None,
                born_at=None,
                branch_module=None,
                user_walk=None,
            ),
            lineage.WalkRecord(
                walk_id="w2",
                flight_id="flight_1",
                parent_walk="w1",
                born_at="seed",
                branch_module="left",
                user_walk="walk_1",
            ),
        ),
    )
    lineage.write_flow_record(tmp_path, record)

    on_disk = json.loads((tmp_path / lineage.FLOW_RECORD_NAME).read_text())
    assert on_disk["format_version"] == 3
    assert on_disk["walks"][1]["user_walk"] == "walk_1"
    assert on_disk["walks"][1]["walk_id"] == "w2"
    # The root walk (user_walk None) omits the key; the round-trip still
    # reconstructs it as None.
    assert "user_walk" not in on_disk["walks"][0]

    read_back = lineage.read_flow_record(tmp_path)
    assert read_back == record
    assert read_back.walks[0].user_walk is None
    assert read_back.walks[1].user_walk == "walk_1"


def test_flow_step_timing_round_trips_at_v4(tmp_path: Path) -> None:
    """started_at and finished_at on FlowStep are the v4 marker."""
    record = lineage.FlowRecord(
        flow_id="flow_20260615_120000",
        lab_name="linear_smoke",
        status="completed",
        created_at="2026-06-15T12:00:00+00:00",
        steps=(
            lineage.FlowStep(
                step_id="emit@w1",
                status="completed",
                duration_s=0.5,
                started_at="2026-06-15T12:00:00+00:00",
                finished_at="2026-06-15T12:00:00.500000+00:00",
            ),
        ),
    )
    lineage.write_flow_record(tmp_path, record)

    on_disk = json.loads((tmp_path / lineage.FLOW_RECORD_NAME).read_text())
    assert on_disk["format_version"] == 4
    assert on_disk["steps"][0]["started_at"] == "2026-06-15T12:00:00+00:00"
    assert on_disk["steps"][0]["finished_at"] == "2026-06-15T12:00:00.500000+00:00"

    read_back = lineage.read_flow_record(tmp_path)
    assert read_back == record


def test_timing_less_flow_step_omits_keys_and_stays_low_version(tmp_path: Path) -> None:
    """No walk fields and no timing keeps version 1 with the timing keys absent."""
    record = lineage.FlowRecord(
        flow_id="flow_20260615_120000",
        lab_name="linear_smoke",
        status="completed",
        created_at="2026-06-15T12:00:00+00:00",
        steps=(
            lineage.FlowStep(step_id="emit@w1", status="completed", duration_s=0.5),
        ),
    )
    lineage.write_flow_record(tmp_path, record)

    on_disk = json.loads((tmp_path / lineage.FLOW_RECORD_NAME).read_text())
    assert on_disk["format_version"] == 1
    assert "started_at" not in on_disk["steps"][0]
    assert "finished_at" not in on_disk["steps"][0]

    read_back = lineage.read_flow_record(tmp_path)
    assert read_back == record
    assert read_back.steps[0].started_at is None


def test_walk_records_without_user_walk_stay_v2(tmp_path: Path) -> None:
    """Walk records without user_walk stay version 2 with the key absent."""
    record = lineage.FlowRecord(
        flow_id="flow_20260613_094100",
        lab_name="diamond_join",
        status="completed",
        created_at="2026-06-13T09:41:00+00:00",
        steps=(lineage.FlowStep(step_id="seed@w1", status="completed"),),
        walks=(
            lineage.WalkRecord(
                walk_id="w2",
                flight_id="f1",
                parent_walk="w1",
                born_at="seed",
                branch_module="left",
            ),
        ),
    )
    lineage.write_flow_record(tmp_path, record)

    on_disk = json.loads((tmp_path / lineage.FLOW_RECORD_NAME).read_text())
    assert on_disk["format_version"] == 2
    assert "user_walk" not in on_disk["walks"][0]

    assert lineage.read_flow_record(tmp_path) == record


def _write_raw_manifest(step_dir: Path, payload: dict[str, object]) -> None:
    """Write a raw (possibly malformed) manifest JSON, bypassing the writer."""
    (step_dir / lineage.STEP_MANIFEST_NAME).write_text(json.dumps(payload))


def test_read_refuses_unknown_format_version(tmp_path: Path) -> None:
    """An unknown format_version is refused, not read best-effort."""
    bad = {"format_version": 999, "step_id": "x", "status": "completed", "seed": 1}
    _write_raw_manifest(tmp_path, bad)
    with pytest.raises(lineage.LineageError, match="format_version"):
        lineage.read_step_manifest(tmp_path)


def test_read_refuses_missing_format_version(tmp_path: Path) -> None:
    """A missing format_version is refused like an unknown one."""
    bad = {"step_id": "x", "status": "completed", "seed": 1}
    _write_raw_manifest(tmp_path, bad)
    with pytest.raises(lineage.LineageError, match="format_version"):
        lineage.read_step_manifest(tmp_path)


def test_read_refuses_missing_file(tmp_path: Path) -> None:
    """Reading a manifest that does not exist refuses with LineageError."""
    with pytest.raises(lineage.LineageError, match="not found"):
        lineage.read_step_manifest(tmp_path / "nope")


def test_read_refuses_non_object_document(tmp_path: Path) -> None:
    """A lineage file that is a JSON array, not an object, is refused."""
    (tmp_path / lineage.FLOW_RECORD_NAME).write_text(json.dumps([1, 2, 3]))
    with pytest.raises(lineage.LineageError, match="not a JSON object"):
        lineage.read_flow_record(tmp_path)
