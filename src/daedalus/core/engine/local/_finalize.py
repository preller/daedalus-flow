"""The local engine's output pass: per-configuration walk dirs and ``final/``.

After every instance has settled in ``.daedalus/`` and the flow record is
durable, :func:`_finalize_outputs` copies the run-once steps into the
per-configuration walk dirs and writes the flow-level ``final/``. It builds on
:class:`_RunPlan` and :func:`_copy_one` from ``_instance``; nothing imports back.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

from daedalus.core import topology
from daedalus.core.engine.protocol import StepStatus

from ._instance import _copy_one, _RunPlan

if TYPE_CHECKING:
    from pathlib import Path


def _materialize_config_walk_dirs(run: _RunPlan) -> None:
    """Copy the run-once steps into the per-configuration walk dirs."""
    # Each configuration walk (one source-to-sink path, one choice per brancher and
    # sibling-collector set) gets [flights/flight_K/]walks/walk_J/ with a byte copy
    # of every step on its path. `NN` is a per-walk sequence, not the plan index.
    from daedalus.core import walks  # noqa: PLC0415 (lazy, pulls networkx)

    by_id = {inst.instance_id: inst for inst in run.walk_plan.instances}
    # walk_J is dense within its flight (reset per flight), so M>1 produces
    # flights/flight_K/walks/walk_1..walk_n, never a global walk index that
    # would collapse all flights into flight_1.
    walk_seq: dict[int | None, int] = {}
    for path in walks.configurations(run.walk_plan):
        flight = _config_flight_number(run, path)
        walk_seq[flight] = walk_seq.get(flight, 0) + 1
        walk_dir = _config_walk_base(run, flight) / (
            f"{topology.WALK_DIR_PREFIX}{walk_seq[flight]}"
        )
        for local_nn, instance_id in enumerate(path, start=1):
            instance = by_id[instance_id]
            dest = walk_dir / f"{local_nn:02d}_{instance.module_id}"
            # A copy OSError is non-fatal; absence marks the failure.
            with contextlib.suppress(OSError):
                _copy_one(run.dir_of[instance_id], dest)


def _config_flight_number(run: _RunPlan, path: tuple[str, ...]) -> int | None:
    """The flight number of a configuration path, or None for a flightless lab."""
    # A path's flight is that of its flight-scope instances; a shared emitter or
    # flight_collector is root-scope and ignored.
    for instance_id in path:
        record = run.record_of.get(run.walk_of[instance_id])
        if record is not None and record.flight_id is not None:
            return run.flight_number_of(instance_id)
    return None


def _config_walk_base(run: _RunPlan, flight_number: int | None) -> Path:
    """The ``walks/`` base, under ``flights/flight_K/`` for a flight-scoped config."""
    base = run.flow_dir
    if flight_number is not None:
        base = (
            base
            / topology.FLIGHTS_DIR
            / (f"{topology.FLIGHT_DIR_PREFIX}{flight_number}")
        )
    return base / topology.WALKS_DIR


def _write_final_dirs(run: _RunPlan) -> None:
    """Write the flow-level ``final/``, a byte mirror of the sink's output."""
    # The sink is the lone terminal instance (out-degree 0). The per-flight final/
    # was written just in time before each flight_collector ran, so only the flow
    # level is written here.
    if len(run.walk_plan.terminal) != 1:
        return
    by_id = {inst.instance_id: inst for inst in run.walk_plan.instances}
    sink = by_id[run.walk_plan.terminal[0]]
    with contextlib.suppress(OSError):
        _copy_one(run.dir_of[sink.instance_id], run.flow_dir / topology.FINAL_DIR)


def _finalize_outputs(run: _RunPlan, flow_status: str) -> None:
    """The post-settle output pass, run only on a completed flow."""
    # A failed run leaves no copies and no final/, so absence means no results.
    # Lineage is written first; both steps copy fixed bytes from .daedalus/.
    if flow_status != StepStatus.COMPLETED.value or not run.walk_plan.terminal:
        return
    _materialize_config_walk_dirs(run)
    _write_final_dirs(run)
