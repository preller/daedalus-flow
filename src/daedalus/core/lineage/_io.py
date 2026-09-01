"""Lineage I/O, the atomic write, versioned read, flow listing and id minting.

Imports the schema from ``_schema`` and adds the on-disk operations. Every file
is written to a sibling ``<name>.tmp``, fsynced, then moved over the target
with ``os.replace``, so a reader sees the old file or the whole new one. The
fixed ``.tmp`` suffix suits the serial single-writer engine. Flow ids sort by
the parsed key ``(timestamp, int(suffix))``, so ``_10`` sorts after ``_2``.
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import shutil
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from daedalus.core import topology

from ._schema import (
    _LEGACY_FORMAT_VERSION,
    FLOW_RECORD_NAME,
    FORMAT_VERSION,
    RESERVED_PREFIX,
    STEP_MANIFEST_NAME,
    FlowRecord,
    LineageError,
    StepManifest,
)

#: Non-terminal flow/step states. A record in one of these claims a live run,
#: so the reconcile path checks the owner before trusting it.
_NON_TERMINAL_STATES: frozenset[str] = frozenset({"running", "submitted"})

#: Sibling lock file for the read-reconcile-write cycle. An advisory ``flock``
#: on it serializes two ``dae`` invocations, so a concurrent reconcile does not
#: clobber a fresh run-start write.
_FLOW_LOCK_NAME = "dae-flow.lock"

#: Cause stamped on each non-terminal step of a reconciled orphan: the owning
#: run is gone, so the step did not finish.
_ORPHAN_CAUSE = "orphaned, run did not finish"

#: Tolerance in seconds for clock skew when matching a process ``create_time``
#: against the stamped one; a recycled pid with another start time reads as dead.
_CREATE_TIME_TOLERANCE_S = 1.0

# A flow_id is ``flow_<YYYYMMDD>_<HHMMSS>`` with an optional ``_<n>`` collision
# suffix (n >= 2). The parser below turns it into the sort key (timestamp, n).
_FLOW_ID_RE = re.compile(r"^flow_(?P<stamp>\d{8}_\d{6})(?:_(?P<suffix>\d+))?$")
_FLOW_ID_STAMP_FMT = "%Y%m%d_%H%M%S"


def _atomic_write_json(target: Path, payload: dict[str, object]) -> None:
    """Write ``payload`` as JSON via a sibling tmp file, fsync and ``os.replace``."""
    # TODO: per-writer tmp names once more than one writer exists.
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, indent=2))
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, target)


def _read_versioned_json(path: Path) -> dict[str, object]:
    """Read a lineage JSON file, refusing an unknown ``format_version``."""
    try:
        text = path.read_text()
    except FileNotFoundError as error:
        raise LineageError(f"lineage file not found: {path}") from error
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise LineageError(f"lineage file is not valid JSON: {path}") from error
    if not isinstance(data, dict):
        raise LineageError(
            f"lineage file is not a JSON object: {path} ({type(data).__name__})."
        )
    version = data.get("format_version")
    if (
        not isinstance(version, int)
        or isinstance(version, bool)
        or not (_LEGACY_FORMAT_VERSION <= version <= FORMAT_VERSION)
    ):
        raise LineageError(
            f"lineage file {path} has unknown format_version {version!r}; "
            f"this build understands versions "
            f"{_LEGACY_FORMAT_VERSION}..{FORMAT_VERSION}."
        )
    return data


def write_step_manifest(step_dir: Path, manifest: StepManifest) -> None:
    """Atomically write ``manifest`` to ``step_dir/dae-manifest.json``."""
    _atomic_write_json(step_dir / STEP_MANIFEST_NAME, manifest.to_json())


def read_step_manifest(step_dir: Path) -> StepManifest:
    """Read and version-check ``step_dir/dae-manifest.json``."""
    return StepManifest.from_json(_read_versioned_json(step_dir / STEP_MANIFEST_NAME))


def write_flow_record(flow_dir: Path, record: FlowRecord) -> None:
    """Atomically write ``record`` to ``flow_dir/dae-flow.json``."""
    _atomic_write_json(flow_dir / FLOW_RECORD_NAME, record.to_json())


def write_flow_outputs(flow_dir: Path, final_step_dir: Path) -> Path:
    """Copy the final module's outputs into ``flow_dir/output/``; return that path.

    A discoverability copy, not lineage: no ``format_version``, not read back,
    reserved ``dae-*`` entries skipped. Staged in a sibling ``output.tmp`` and
    moved over with ``os.replace``; stale staging and destination are removed first.
    """
    dst = flow_dir / topology.FLOW_OUTPUT_DIR
    staging = flow_dir / (topology.FLOW_OUTPUT_DIR + ".tmp")
    for path in (staging, dst):
        if path.exists():
            shutil.rmtree(path)
    shutil.copytree(
        final_step_dir,
        staging,
        ignore=shutil.ignore_patterns(RESERVED_PREFIX + "*"),
    )
    os.replace(staging, dst)
    return dst


def read_flow_record(flow_dir: Path) -> FlowRecord:
    """Read and version-check ``flow_dir/dae-flow.json``."""
    return FlowRecord.from_json(_read_versioned_json(flow_dir / FLOW_RECORD_NAME))


def _owner_is_live(pid: int | None, create_time: float | None) -> bool:
    """True iff a live process matches the stamped ``(pid, create_time)``."""
    # An unstamped record predates the owner stamp; its run is gone.
    if pid is None or create_time is None:
        return False
    import psutil  # noqa: PLC0415 (lazy: orchestration-only)

    try:
        proc = psutil.Process(pid)
        skew = abs(float(proc.create_time()) - create_time)
    except (psutil.NoSuchProcess, psutil.Error):
        return False
    return skew <= _CREATE_TIME_TOLERANCE_S


def reconcile_flow_record(record: FlowRecord) -> FlowRecord:
    """Flip a crashed-run orphan to ``failed``; return any other record as is.

    A ``running`` or ``submitted`` record whose owner is not a live process is an
    orphan. The reconciled record reads ``failed``, every non-terminal step is
    flipped to ``failed`` with the orphan cause, and the owner stamp is cleared.
    """
    if record.status not in _NON_TERMINAL_STATES:
        return record
    if _owner_is_live(record.owner_pid, record.owner_create_time):
        return record
    failed_steps = tuple(
        replace(step, status="failed", error=_ORPHAN_CAUSE)
        if step.status in _NON_TERMINAL_STATES
        else step
        for step in record.steps
    )
    return replace(
        record,
        status="failed",
        steps=failed_steps,
        owner_pid=None,
        owner_create_time=None,
    )


def read_flow_record_reconciled(flow_dir: Path) -> FlowRecord:
    """Read ``dae-flow.json``, reconciling a crashed-run orphan on the way out.

    ``dae flow status`` and the start of the next ``dae lab run`` both read
    through here, so a record stranded by a crash reports as ``failed``. The
    cycle runs under an advisory ``flock``; a changed record is rewritten atomically.
    """
    flow_dir.mkdir(parents=True, exist_ok=True)
    lock_path = flow_dir / _FLOW_LOCK_NAME
    with open(lock_path, "a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            record = read_flow_record(flow_dir)
            reconciled = reconcile_flow_record(record)
            if reconciled != record:
                write_flow_record(flow_dir, reconciled)
            return reconciled
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _flow_sort_key(flow_id: str) -> tuple[int, int]:
    """Sort key ``(timestamp, suffix)`` of a flow_id; a non-matching id sorts first."""
    match = _FLOW_ID_RE.match(flow_id)
    if match is None:
        return (-1, -1)
    stamp = int(datetime.strptime(match["stamp"], _FLOW_ID_STAMP_FMT).timestamp())
    suffix = int(match["suffix"]) if match["suffix"] is not None else 1
    return (stamp, suffix)


def list_flows(output_root: Path) -> list[str]:
    """Return the flow ids under ``output_root/flows``, oldest to newest.

    Sorted by the parsed key ``(timestamp, int(suffix))`` so "latest" (the last
    entry) is correct even past 10 same-second collisions. Returns ``[]`` when
    no ``flows/`` directory exists (a valid empty query).
    """
    flows_root = output_root / "flows"
    if not flows_root.is_dir():
        return []
    ids = [p.name for p in flows_root.iterdir() if p.is_dir()]
    return sorted(ids, key=_flow_sort_key)


def new_flow_id(now: datetime, existing: list[str] | None = None) -> str:
    """Build a ``flow_<YYYYMMDD>_<HHMMSS>`` id, suffixed on a same-second clash.

    ``now`` is a timezone-aware UTC datetime. When ``existing`` holds the same
    timestamp, the next free ``_<n>`` suffix (n >= 2) is appended. The lab name
    is not part of the id.
    """
    base = f"flow_{now.strftime(_FLOW_ID_STAMP_FMT)}"
    taken = set(existing or [])
    if base not in taken:
        return base
    suffix = 2
    while f"{base}_{suffix}" in taken:
        suffix += 1
    return f"{base}_{suffix}"
