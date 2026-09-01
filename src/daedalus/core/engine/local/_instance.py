"""Run-once runner and per-instance wiring for the local engine.

Holds :class:`_RunPlan` (immutable per-run wiring), :func:`_run_one_instance`
with its :class:`_StepOutcome`, the FlowContext wiring by role, the atomic copy
primitives :func:`_copy_one` and :func:`_copy_merged`, and the mutable
:class:`_RunState`. Each G* instance runs once under
``.daedalus/<token>/<NN>_<module>/``; ``_finalize`` copies those results into
the per-configuration walk dirs. Nothing here references ``LocalEngine``.
"""

from __future__ import annotations

import os
import shutil
import time
import traceback
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import daedalus.flow as dae
from daedalus.core import lineage, topology
from daedalus.core.engine.isolation import (
    ModuleEnv,
    resolve_module,
    strategy_for,
)
from daedalus.core.engine.protocol import LabConfig, StepStatus
from daedalus.core.engine.step import (
    build_context,
    classify_step_failure,
    derive_seed,
)
from daedalus.flow import Role

if TYPE_CHECKING:
    from daedalus.core.walks import Instance, WalkPlan, WalkRecord


# The full-traceback sidecar a failed step drops beside its output. The manifest
# error stays a clean one-liner; the multi-frame traceback lands here so the CLI
# can print a trimmed cause inline and point at this file for the rest.
STEP_ERROR_LOG_NAME = "step-error.log"

# Decimal places kept on a step's wall-clock duration (microsecond resolution).
_DURATION_DECIMALS = 6


def _save_step_error_log(step_dir: Path) -> Path | None:
    """Write the live traceback to ``step_dir/step-error.log``; ``None`` on OSError."""
    # Called inside the except block of _run_one_instance, so format_exc sees the
    # live exception. A failed save never masks the step failure itself.
    try:
        step_dir.mkdir(parents=True, exist_ok=True)
        log_path = step_dir / STEP_ERROR_LOG_NAME
        log_path.write_text(traceback.format_exc())
    except OSError:
        return None
    return log_path


def _daedalus_dir(daedalus_root: Path, instance: Instance) -> Path:
    """The run-once dir of one instance, ``.daedalus/<token>/<NN>_<module>/``."""
    # `NN` is the module's static plan index, distinct from the per-walk config-dir
    # numbering; this dir carries the manifest and seed the walk dirs are copied from.
    return (
        daedalus_root / instance.walk_id / f"{instance.index:02d}_{instance.module_id}"
    )


@dataclass(frozen=True)
class _RunPlan:
    """The immutable per-run wiring derived from the WalkPlan."""

    flow_dir: Path
    daedalus_root: Path  # the run-once staging root, .daedalus/ in the cwd
    config: LabConfig
    walk_plan: WalkPlan
    dir_of: dict[str, Path]  # instance id -> its run-once dir
    parents_of: dict[str, tuple[str, ...]]  # instance id -> sorted G* parents
    record_of: dict[str, WalkRecord]  # walk id -> walk record
    user_walk_of: dict[str, str | None]  # internal walk id -> user-facing walk_J
    has_flights: bool  # whether the lab has a flight axis
    module_dir_of: dict[str, Path]  # module id -> static module dir
    role_of: dict[str, str]  # module id -> role

    @property
    def walk_of(self) -> dict[str, str]:
        """Instance id -> its internal walk id (derived over the plan instances)."""
        return {inst.instance_id: inst.walk_id for inst in self.walk_plan.instances}

    def walk_input_dirs(self, collector_instance_id: str) -> dict[str, Path]:
        """A walk-collector's ``ctx.walk_inputs``: user-facing ``walk_J`` -> tail dir.

        The values are the run-once tail dirs of each child branch, not the
        per-walk copies; ``scheduler.resolve_walk_inputs`` does the lookup and only
        the keys are relabeled here.
        """
        from daedalus.core.engine import scheduler  # noqa: PLC0415 (lazy)

        resolved = scheduler.resolve_walk_inputs(
            self.walk_plan,
            collector_instance_id,
            lambda iid: str(self.dir_of[iid]),
        )
        out: dict[str, Path] = {}
        for internal_walk_id, path in resolved.items():
            user = self.user_walk_of.get(internal_walk_id) or internal_walk_id
            out[user] = Path(path)
        return out

    def flight_number_of(self, instance_id: str) -> int:
        """The 1-based flight number K of a flight-scope instance (from its walk).

        Derived once from the instance's walk record flight id (``fK`` -> K), the
        single source of the runtime flight index; never re-counted downstream.
        """
        from daedalus.core import flights  # noqa: PLC0415 (lazy, pulls networkx)

        walk_id = self.walk_of[instance_id]
        flight_id = self.record_of[walk_id].flight_id
        assert flight_id is not None  # noqa: S101 (caller passes a flight-scope tail)
        return flights.flight_index_of(flight_id)

    def flight_final_dir(self, flight_number: int) -> Path:
        """The per-flight ``flights/flight_K/final/`` dir (the flight tail mirror)."""
        flight = f"{topology.FLIGHT_DIR_PREFIX}{flight_number}"
        return self.flow_dir / topology.FLIGHTS_DIR / flight / topology.FINAL_DIR

    def flight_input_dirs(self, collector_instance_id: str) -> dict[str, Path]:
        """A flight-collector's ``flight_inputs``: ``flight_K`` -> per-flight final/.

        Each value is the flight's merged ``final/`` dir, the union of its tails
        written by :func:`_materialize_flight_finals`, so several G* parents in one
        flight map to one entry. M=1 yields ``flight_1`` alone.
        """
        parents = self.parents_of.get(collector_instance_id, ())
        out: dict[str, Path] = {}
        for parent in parents:
            k = self.flight_number_of(parent)
            out[f"{topology.FLIGHT_DIR_PREFIX}{k}"] = self.flight_final_dir(k)
        return out


def _instance_input(run: _RunPlan, instance: Instance) -> Path:
    """The one input dir of an emitter or transform instance."""
    # The source instance, which has no G* parent, reads the lab's input/; any
    # other reads its single on-walk parent's output dir. A branched transform
    # has exactly one on-walk parent because validate refuses the broadcast case.
    parents = run.parents_of.get(instance.instance_id, ())
    if not parents:
        return run.config.lab_dir / "input"
    return run.dir_of[parents[0]]


def _instance_flight_label(run: _RunPlan, instance: Instance) -> str:
    """The user-facing ``flight_K`` an instance runs in; ``flight_1`` off the axis."""
    # A flight-scope instance gets its own flight_K so a per-flight step can pick
    # its roster row by ctx.flight_id; the root-scope emitter and flight_collector
    # keep the flight_1 default.
    record = run.record_of[instance.walk_id]
    if record.flight_id is None:
        return f"{topology.FLIGHT_DIR_PREFIX}1"
    return f"{topology.FLIGHT_DIR_PREFIX}{run.flight_number_of(instance.instance_id)}"


def _materialize_flight_finals(run: _RunPlan, collector_instance_id: str) -> None:
    """Mirror each flight's tails into its ``flights/flight_K/final/``."""
    # A flight can end in several sibling walk_collectors, so final/ is the union
    # of its tails. One tail goes through _copy_one and stays byte-identical;
    # several go through _copy_merged. Every tail is durable before the collector.
    by_flight: dict[int, list[str]] = {}
    for parent in run.parents_of.get(collector_instance_id, ()):
        by_flight.setdefault(run.flight_number_of(parent), []).append(parent)
    for k, parents in sorted(by_flight.items()):
        srcs = [run.dir_of[p] for p in sorted(parents)]
        dst = run.flight_final_dir(k)
        if len(srcs) == 1:
            _copy_one(srcs[0], dst)
        else:
            _copy_merged(srcs, dst)


def _instance_context(
    run: _RunPlan, instance: Instance, seed: int, output_dir: Path
) -> dae.FlowContext:
    """Wire one instance's FlowContext: inputs by role, ``ctx.walk_id`` set."""
    # walk_collector gets walk_inputs keyed by user-facing walk_J; flight_collector
    # gets flight_inputs keyed by flight_K, materialized just in time; emitter and
    # transform read one positional input dir.
    role = Role(run.role_of[instance.module_id])
    flight_label = _instance_flight_label(run, instance)
    if role is Role.WALK_COLLECTOR:
        return build_context(
            step_id=instance.module_id,
            role=role,
            output_dir=output_dir,
            walk_inputs=run.walk_input_dirs(instance.instance_id),
            walk_id=instance.walk_id,
            flight_id=flight_label,
            seed=seed,
        )
    if role is Role.FLIGHT_COLLECTOR:
        _materialize_flight_finals(run, instance.instance_id)
        return build_context(
            step_id=instance.module_id,
            role=role,
            output_dir=output_dir,
            flight_inputs=run.flight_input_dirs(instance.instance_id),
            walk_id=instance.walk_id,
            flight_id=flight_label,
            seed=seed,
        )
    return build_context(
        step_id=instance.module_id,
        role=role,
        output_dir=output_dir,
        input_dir=_instance_input(run, instance),
        walk_id=instance.walk_id,
        flight_id=flight_label,
        seed=seed,
    )


def _copy_one(src: Path, dst: Path) -> None:
    """Atomically copy ``src``'s module outputs into ``dst``, excluding ``dae-*``."""
    # Stage in a sibling .tmp dir, then os.replace into place; stale staging or
    # destination is removed first so a crashed prior attempt never wedges. The
    # dae-* exclusion keeps a copy from carrying a second manifest.
    staging = dst.with_name(dst.name + ".tmp")
    for path in (staging, dst):
        if path.exists():
            shutil.rmtree(path)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        src, staging, ignore=shutil.ignore_patterns(lineage.RESERVED_PREFIX + "*")
    )
    try:
        os.replace(staging, dst)
    except OSError:
        # Remove the staging dir so no half-written copy survives, then re-raise
        # for the caller's non-fatal suppression.
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        raise


def _copy_merged(srcs: list[Path], dst: Path) -> None:
    """Merge several module output dirs into ``dst`` atomically, their union."""
    # The multi-tail counterpart of _copy_one, for a flight final/ that gathers
    # sibling walk_collectors. On a same-name file the later src wins, which is
    # deterministic because srcs arrive in sorted instance order.
    ignore = shutil.ignore_patterns(lineage.RESERVED_PREFIX + "*")
    staging = dst.with_name(dst.name + ".tmp")
    for path in (staging, dst):
        if path.exists():
            shutil.rmtree(path)
    dst.parent.mkdir(parents=True, exist_ok=True)
    staging.mkdir(parents=True)
    for src in srcs:
        shutil.copytree(src, staging, ignore=ignore, dirs_exist_ok=True)
    try:
        os.replace(staging, dst)
    except OSError:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        raise


@dataclass(frozen=True)
class _StepOutcome:
    """The result of running one instance: its terminal manifest and any error."""

    manifest: lineage.StepManifest
    duration_s: float
    status: StepStatus
    error: str | None
    missing_package: str | None = None  # absent top-level package on a load failure
    error_code: str | None = None  # dae.step.* code of the failure, None on success


def _run_one_instance(run: _RunPlan, instance: Instance) -> _StepOutcome:
    """Run one instance, writing its running and then its terminal manifest."""
    # The seed is re-keyed on the instance id; the step dir is the run-once dir
    # and the per-walk copies come later in finalize. Timing is measured here,
    # since step.py records none.
    instance_id = instance.instance_id
    step_dir = run.dir_of[instance_id]
    seed = derive_seed(run.config.seed, instance_id)
    record = run.record_of[instance.walk_id]
    started_at = datetime.now(UTC).isoformat()
    lineage.write_step_manifest(
        step_dir,
        lineage.StepManifest(
            step_id=instance.module_id,
            status=StepStatus.RUNNING.value,
            seed=seed,
            started_at=started_at,
            flight_id=record.flight_id,
            walk_id=instance.walk_id,
            instance_id=instance_id,
        ),
    )

    start = time.monotonic()
    error: str | None = None
    error_code: str | None = None
    missing_package: str | None = None
    try:
        ctx = _instance_context(run, instance, seed, step_dir)
        module_dir = run.module_dir_of[instance.module_id]
        # The isolation strategy comes from the module's own dae-module.yaml
        # preference, the lab policy and K. It raises StepError on failure, so
        # every backend reaches the manifest write below through one path.
        env = ModuleEnv.from_module_dir(instance.module_id, module_dir)
        resolution = resolve_module(env, run.config.isolation, run.config.max_workers)
        strategy_for(resolution.strategy).launch(module_dir, ctx)
    except Exception as step_error:  # noqa: BLE001 (recorded as a failed manifest)
        error = str(step_error)
        # Typed missing-dep signal set by load_entry's StepError; absent (None)
        # for every other failure. getattr keeps this tolerant of non-StepError.
        missing_package = getattr(step_error, "missing_package", None)
        # Classify how the step failed into its stable dae.step.* code from the
        # typed signals (returncode/stderr are subprocess-only, None/"" ambient).
        error_code = str(
            classify_step_failure(
                error,
                missing_package=missing_package,
                returncode=getattr(step_error, "returncode", None),
                stderr=getattr(step_error, "stderr", "") or "",
            )
        )
        # Save the full traceback beside the step output; the manifest error
        # stays a one-liner the CLI prints with a pointer to the file.
        _save_step_error_log(step_dir)
    duration = round(time.monotonic() - start, _DURATION_DECIMALS)

    status = StepStatus.FAILED if error is not None else StepStatus.COMPLETED
    manifest = lineage.StepManifest(
        step_id=instance.module_id,
        status=status.value,
        seed=seed,
        started_at=started_at,
        finished_at=datetime.now(UTC).isoformat(),
        duration_s=duration,
        error=error,
        error_code=error_code,
        flight_id=record.flight_id,
        walk_id=instance.walk_id,
        instance_id=instance_id,
    )
    lineage.write_step_manifest(step_dir, manifest)
    return _StepOutcome(
        manifest=manifest,
        duration_s=duration,
        status=status,
        error=error,
        missing_package=missing_package,
        error_code=error_code,
    )


@dataclass
class _RunState:
    """The mutable bookkeeping of one flow run, identity plus live status maps."""

    flow_id: str
    flow_dir: Path
    config: LabConfig
    created_at: str
    walk_plan: WalkPlan
    module_status: dict[str, str]  # instance id -> status value, updated in place
    durations: dict[str, float]  # instance id -> wall-clock seconds
    user_walk_of: dict[str, str | None]
    started_at: dict[str, str | None] = field(default_factory=dict)
    finished_at: dict[str, str | None] = field(default_factory=dict)
    error: str | None = None  # the first failure's text
    missing_package: str | None = None  # the first failure's missing package
    # instance id -> error text, so each failed step's cause reaches the flow record
    step_errors: dict[str, str] = field(default_factory=dict)
    # instance id -> dae.step.* code, parallel to step_errors
    step_error_codes: dict[str, str] = field(default_factory=dict)

    def write_flow_record(self, status: str) -> None:
        """Write the per-flow record with instance-keyed steps and walk records.

        Each walk record carries the presentation-only ``user_walk``. A ``running``
        write stamps this process's ``(pid, create_time)`` as the owner, so the read
        path can tell a live run from a stranded one; a terminal write clears it.
        """
        owner_pid, owner_create_time = self._owner_stamp(status)
        flow_steps = tuple(
            lineage.FlowStep(
                step_id=instance.instance_id,
                status=self.module_status[instance.instance_id],
                duration_s=self.durations.get(instance.instance_id),
                started_at=self.started_at.get(instance.instance_id),
                finished_at=self.finished_at.get(instance.instance_id),
                error=self.step_errors.get(instance.instance_id),
                error_code=self.step_error_codes.get(instance.instance_id),
            )
            for instance in self.walk_plan.instances
        )
        walk_records = tuple(
            lineage.WalkRecord(
                walk_id=record.walk_id,
                flight_id=record.flight_id,
                parent_walk=record.parent_walk,
                born_at=record.born_at,
                branch_module=record.branch_module,
                user_walk=self.user_walk_of.get(record.walk_id),
            )
            for record in self.walk_plan.walks
        )
        lineage.write_flow_record(
            self.flow_dir,
            lineage.FlowRecord(
                flow_id=self.flow_id,
                lab_name=self.config.lab_name,
                status=status,
                created_at=self.created_at,
                steps=flow_steps,
                walks=walk_records,
                engine=self.config.engine,
                max_workers=self.config.max_workers,
                owner_pid=owner_pid,
                owner_create_time=owner_create_time,
            ),
        )

    @staticmethod
    def _owner_stamp(status: str) -> tuple[int | None, float | None]:
        """Owner stamp for a ``running`` write; ``(None, None)`` for a terminal one."""
        # Only the running record carries the stamp, so the durable end-state
        # bytes never move.
        if status != StepStatus.RUNNING.value:
            return None, None
        import psutil  # noqa: PLC0415 (lazy, orchestration-only; keeps the shims stdlib-only)

        return os.getpid(), psutil.Process().create_time()
