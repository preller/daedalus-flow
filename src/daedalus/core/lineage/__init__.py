"""The on-disk run record, per-step manifests and the per-flow record.

The core-layer reader and writer for the lineage tree under
``dae-outputs/flows/<flow_id>/``: ``dae-flow.json`` plus one
``<NN>_<module_id>/dae-manifest.json`` per step. ``_schema`` holds the
constants and dataclasses, ``_io`` the atomic write, versioned read and flow
listing; this package re-exports both. Every file carries ``format_version``
(1 through 4), and the reader refuses a missing or unknown version.
"""

from __future__ import annotations

from daedalus.core.lineage._io import (
    list_flows,
    new_flow_id,
    read_flow_record,
    read_flow_record_reconciled,
    read_step_manifest,
    reconcile_flow_record,
    write_flow_outputs,
    write_flow_record,
    write_step_manifest,
)
from daedalus.core.lineage._schema import (
    FLOW_RECORD_NAME,
    FORMAT_VERSION,
    RESERVED_PREFIX,
    STEP_MANIFEST_NAME,
    FlowRecord,
    FlowStep,
    LineageError,
    StepManifest,
    WalkRecord,
)

__all__ = [
    "FLOW_RECORD_NAME",
    "FORMAT_VERSION",
    "RESERVED_PREFIX",
    "STEP_MANIFEST_NAME",
    "FlowRecord",
    "FlowStep",
    "LineageError",
    "StepManifest",
    "WalkRecord",
    "list_flows",
    "new_flow_id",
    "read_flow_record",
    "read_flow_record_reconciled",
    "read_step_manifest",
    "reconcile_flow_record",
    "write_flow_outputs",
    "write_flow_record",
    "write_step_manifest",
]
