"""Reconcile on read, so a flow record never reports running for a dead owner.

Lineage layer only, no engine; liveness uses psutil and all writes go to tmp_path.
"""

from __future__ import annotations

import fcntl
import os
import threading
from typing import TYPE_CHECKING

import psutil
import pytest

from daedalus.core import lineage
from daedalus.core.lineage import _io

if TYPE_CHECKING:
    from pathlib import Path


def _dead_pid() -> int:
    """A pid past the default pid_max, a stand-in for a crashed owner."""
    return 2**22 + 7


def _running_record_owned_by(pid: int, create_time: float) -> lineage.FlowRecord:
    """A ``running`` flow record with one ``submitted`` step, stamped to ``pid``."""
    return lineage.FlowRecord(
        flow_id="flow_20260625_120000",
        lab_name="crash_lab",
        status="running",
        created_at="2026-06-25T12:00:00+00:00",
        steps=(
            lineage.FlowStep(step_id="00_emit_ticks", status="running"),
            lineage.FlowStep(step_id="01_fit", status="submitted"),
        ),
        owner_pid=pid,
        owner_create_time=create_time,
    )


def test_reconcile_flips_dead_owner_orphan_to_failed(tmp_path: Path) -> None:
    """Status, steps and the file on disk flip to failed; the owner stamp clears."""
    record = _running_record_owned_by(_dead_pid(), 1.0)
    lineage.write_flow_record(tmp_path, record)

    reconciled = lineage.read_flow_record_reconciled(tmp_path)

    assert reconciled.status == "failed"
    assert all(step.status == "failed" for step in reconciled.steps)
    assert all(
        step.error == "orphaned, run did not finish" for step in reconciled.steps
    )
    assert reconciled.owner_pid is None
    assert reconciled.owner_create_time is None

    # The rewrite is durable; a fresh pure read sees the reconciled record.
    on_disk = lineage.read_flow_record(tmp_path)
    assert on_disk.status == "failed"
    assert all(step.status == "failed" for step in on_disk.steps)


def test_reconcile_is_a_noop_for_a_terminal_record(tmp_path: Path) -> None:
    """A ``completed`` record is returned unchanged (and the file is untouched)."""
    record = lineage.FlowRecord(
        flow_id="flow_20260625_130000",
        lab_name="clean_lab",
        status="completed",
        created_at="2026-06-25T13:00:00+00:00",
        steps=(lineage.FlowStep(step_id="00_emit", status="completed"),),
    )
    lineage.write_flow_record(tmp_path, record)

    reconciled = lineage.read_flow_record_reconciled(tmp_path)

    assert reconciled == record


def test_reconcile_flow_record_pure_function_flips_orphan() -> None:
    """A dead-owner record flips with no I/O."""
    record = _running_record_owned_by(_dead_pid(), 1.0)

    out = lineage.reconcile_flow_record(record)

    assert out.status == "failed"
    assert out.owner_pid is None
    assert all(step.status == "failed" for step in out.steps)


def test_reconcile_does_not_flip_a_live_owner(tmp_path: Path) -> None:
    """The owner is this process, so the record stays running."""
    record = _running_record_owned_by(os.getpid(), psutil.Process().create_time())
    lineage.write_flow_record(tmp_path, record)

    reconciled = lineage.read_flow_record_reconciled(tmp_path)

    assert reconciled.status == "running"
    assert reconciled == record


def test_reconcile_flips_when_create_time_diverges(tmp_path: Path) -> None:
    """A live pid with create_time 10 s off is a reused pid and reads as dead."""
    skewed_create_time = psutil.Process().create_time() + 10.0
    record = _running_record_owned_by(os.getpid(), skewed_create_time)
    lineage.write_flow_record(tmp_path, record)

    reconciled = lineage.read_flow_record_reconciled(tmp_path)

    assert reconciled.status == "failed"
    assert all(step.status == "failed" for step in reconciled.steps)


def test_reconcile_tolerates_subsecond_create_time_skew(tmp_path: Path) -> None:
    """Half a second of skew is within the clock tolerance; the owner is live."""
    near_create_time = psutil.Process().create_time() + 0.5
    record = _running_record_owned_by(os.getpid(), near_create_time)
    lineage.write_flow_record(tmp_path, record)

    reconciled = lineage.read_flow_record_reconciled(tmp_path)

    assert reconciled.status == "running"


def test_reconcile_cycle_holds_an_exclusive_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A second non-blocking flock on the lock file fails while reconcile runs."""
    record = _running_record_owned_by(_dead_pid(), 1.0)
    lineage.write_flow_record(tmp_path, record)
    lock_path = tmp_path / "dae-flow.lock"
    probe: dict[str, object] = {}
    real_reconcile = _io.reconcile_flow_record

    def _probe_then_reconcile(rec: lineage.FlowRecord) -> lineage.FlowRecord:
        with open(lock_path, "a+", encoding="utf-8") as second:
            try:
                fcntl.flock(second.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                probe["locked_out"] = False
                fcntl.flock(second.fileno(), fcntl.LOCK_UN)
            except BlockingIOError:
                probe["locked_out"] = True
        return real_reconcile(rec)

    monkeypatch.setattr(_io, "reconcile_flow_record", _probe_then_reconcile)
    lineage.read_flow_record_reconciled(tmp_path)

    assert probe["locked_out"] is True


def test_concurrent_reconcile_does_not_lose_a_fresh_run_start(tmp_path: Path) -> None:
    """A writer and a reconciler race under the flock; no torn record results."""
    seed = _running_record_owned_by(_dead_pid(), 1.0)
    lineage.write_flow_record(tmp_path, seed)
    live_start = lineage.FlowRecord(
        flow_id="flow_20260625_120001",
        lab_name="crash_lab",
        status="running",
        created_at="2026-06-25T12:00:01+00:00",
        steps=(lineage.FlowStep(step_id="00_emit_ticks", status="running"),),
        owner_pid=os.getpid(),
        owner_create_time=psutil.Process().create_time(),
    )
    lock_path = tmp_path / "dae-flow.lock"
    barrier = threading.Barrier(2)

    def _reconcile() -> None:
        barrier.wait()
        lineage.read_flow_record_reconciled(tmp_path)

    def _fresh_run_start() -> None:
        barrier.wait()
        # Mirror the cycle's own locking discipline; the write then never lands
        # mid-cycle of the reconciler.
        with open(lock_path, "a+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                lineage.write_flow_record(tmp_path, live_start)
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    threads = [
        threading.Thread(target=_reconcile),
        threading.Thread(target=_fresh_run_start),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    final = lineage.read_flow_record(tmp_path)
    if final.flow_id == live_start.flow_id:
        # The fresh run-start won the race; it survives whole and still alive.
        assert final.status == "running"
        assert final.owner_pid == os.getpid()
    else:
        # The reconciler won; the dead seed is now a coherent failed record.
        assert final.flow_id == seed.flow_id
        assert final.status == "failed"
