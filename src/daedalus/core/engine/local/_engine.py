"""LocalEngine, the default in-process engine over the static walk model.

``execute_dag`` propagates a lab into a :class:`~daedalus.core.walks.WalkPlan`,
runs the emitter and expands M flights. The rest dispatches over G* through
:mod:`~daedalus.core.engine.scheduler`, each instance running once into the
``.daedalus/`` store; the results are copied into the per-configuration walk dirs.
``resume_flow`` replays a recorded plan. ``walks`` and the scheduler are imported
lazily so networkx stays off the ``daedalus.core.engine`` import path.
"""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from daedalus.core import lineage, topology
from daedalus.core.engine.protocol import (
    ExecutionResult,
    FlowStatus,
    LabConfig,
    StepStatus,
)
from daedalus.flow import Role

from ._finalize import _finalize_outputs
from ._instance import (
    _daedalus_dir,
    _run_one_instance,
    _RunPlan,
    _RunState,
    _StepOutcome,
)

if TYPE_CHECKING:
    import networkx as nx

    from daedalus.core.recipe import ExecutionPlan
    from daedalus.core.walks import Instance, WalkPlan


def _record_error_code(
    state: _RunState, instance_id: str, error_code: str | None
) -> None:
    """Record a failed instance's ``dae.step.*`` code on the run state, if any."""
    if error_code is not None:
        state.step_error_codes[instance_id] = error_code


class LocalEngine:
    """In-process K=1 walk engine: propagate, dispatch over G*, write lineage."""

    def execute_dag(self, dag: nx.DiGraph, config: LabConfig) -> ExecutionResult:
        """Propagate the lab, dispatch its instances over G* and write the tree.

        The emitter runs first and sets M; ``_dispatch`` drives the scheduler, each
        callback runs ``_run_one_instance`` into ``.daedalus/``, and finalize copies
        the store into the walk dirs. After a failure the rest stay SUBMITTED.
        """
        # walks pulls networkx, which importing daedalus.core.engine must not.
        from daedalus.core import recipe, walks  # noqa: PLC0415

        # The Protocol types dag as nx.DiGraph; the CLI passes the ExecutionPlan.
        plan: ExecutionPlan = dag
        spec = recipe.load_recipe(config.lab_dir / "lab.yaml")
        propagated = walks.propagate(spec, config.lab_dir)
        if isinstance(propagated, walks.WalkDefect):
            # The run path has already validated, so a defect here is a caller
            # contract violation rather than a user error.
            msg = (
                f"walks.propagate refused an already-validated lab: "
                f"{propagated.token} ({propagated.reason})"
            )
            raise RuntimeError(msg)

        flow_id = lineage.new_flow_id(
            datetime.now(UTC), lineage.list_flows(config.output_root)
        )
        flow_dir = config.output_root / "flows" / flow_id
        flow_dir.mkdir(parents=True, exist_ok=True)

        run = self._build_run_plan(flow_dir, config, propagated, plan)
        # Clear any prior .daedalus/ so the store holds only this run's instances;
        # it is ephemeral and `dae lab clean` sweeps it.
        if run.daedalus_root.exists():
            shutil.rmtree(run.daedalus_root)

        created_at = datetime.now(UTC).isoformat()
        # Runtime fan-out (M>1): run the emitter first, read M from its output
        # partition, then expand the M=1 skeleton into M flights before dispatching
        # the rest. An empty partition (M=0) is a successful zero-flight run.
        emitter = self._emitter_instance(propagated)
        emitter_id = emitter.instance_id if emitter is not None else None
        emitter_done = _run_one_instance(run, emitter) if emitter is not None else None
        run, propagated, empty_partition = self._expand_for_flights(
            flow_dir, config, plan, propagated, run, emitter_done
        )

        state = _RunState(
            flow_id=flow_id,
            flow_dir=flow_dir,
            config=config,
            created_at=created_at,
            walk_plan=propagated,
            module_status={
                inst.instance_id: StepStatus.SUBMITTED.value
                for inst in propagated.instances
            },
            durations={},
            user_walk_of=run.user_walk_of,
        )
        if emitter_done is not None and emitter_id is not None:
            # The emitter already settled into .daedalus/ above; carry its status
            # so the scheduler treats it as done (it never re-runs the source).
            state.module_status[emitter_id] = emitter_done.status.value
            state.durations[emitter_id] = emitter_done.duration_s
            state.started_at[emitter_id] = emitter_done.manifest.started_at
            state.finished_at[emitter_id] = emitter_done.manifest.finished_at
            if emitter_done.error is not None:
                state.error = emitter_done.error
                state.step_errors[emitter_id] = emitter_done.error
                _record_error_code(state, emitter_id, emitter_done.error_code)
                state.missing_package = emitter_done.missing_package

        # Write the running flow record before dispatch, so the walk records are
        # durable from the first write.
        state.write_flow_record(StepStatus.RUNNING.value)
        if state.error is None and not empty_partition:
            done = {emitter_id} if emitter_id is not None else set()
            self._dispatch(run, state, already_done=done)

        flow_status = (
            StepStatus.FAILED.value
            if state.error is not None
            else StepStatus.COMPLETED.value
        )
        finished_at = datetime.now(UTC).isoformat()
        state.write_flow_record(flow_status)
        if not empty_partition:
            # An empty partition (M=0) writes no flights/ dir and no final/:
            # there is nothing to materialize, so finalize is skipped entirely.
            _finalize_outputs(run, flow_status)
        return ExecutionResult(
            flow_id=flow_id,
            status=flow_status,
            lab_name=config.lab_name,
            module_status=dict(state.module_status),
            started_at=state.created_at,
            finished_at=finished_at,
            error=state.error,
            missing_package=state.missing_package,
            empty_partition=empty_partition,
        )

    @staticmethod
    def _emitter_instance(walk_plan: WalkPlan) -> Instance | None:
        """The single emitter instance, or None for a lab without an emitter."""
        for inst in walk_plan.instances:
            if Role(walk_plan.roles[inst.module_id]) is Role.EMITTER:
                return inst
        return None

    def _expand_for_flights(
        self,
        flow_dir: Path,
        config: LabConfig,
        plan: ExecutionPlan,
        propagated: WalkPlan,
        run: _RunPlan,
        emitter_done: _StepOutcome | None,
    ) -> tuple[_RunPlan, WalkPlan, bool]:
        """Read M from the settled emitter and expand the plan to M flights."""
        # Returns the run plan, the walk plan and whether the partition was empty.
        # No emitter, a failed emitter or M=1 pass the inputs through unchanged;
        # M=0 short-circuits to an empty zero-flight run.
        from daedalus.core import flights  # noqa: PLC0415 (lazy, pulls networkx)

        if emitter_done is None or emitter_done.error is not None:
            return run, propagated, False
        emitter = self._emitter_instance(propagated)
        assert emitter is not None  # noqa: S101 (emitter_done implies an emitter)
        m = flights.read_partition_count(run.dir_of[emitter.instance_id])
        if m == 0:
            return run, propagated, True
        if m == 1:
            return run, propagated, False
        expanded = flights.expand_flights(propagated, m)
        rebuilt = self._build_run_plan(flow_dir, config, expanded, plan)
        return rebuilt, expanded, False

    @staticmethod
    def _build_run_plan(
        flow_dir: Path,
        config: LabConfig,
        walk_plan: WalkPlan,
        plan: ExecutionPlan,
    ) -> _RunPlan:
        """Derive the immutable per-run wiring from the WalkPlan and ExecutionPlan."""
        # .daedalus/ lives in the cwd beside dae-outputs/; every instance's run-once
        # dir is keyed under it, and the user-facing walk dirs are copies of these.
        from daedalus.core import walks  # noqa: PLC0415 (lazy, pulls networkx)

        daedalus_root = config.output_root.parent / topology.INTERNAL_DIR
        parents: dict[str, list[str]] = {
            inst.instance_id: [] for inst in walk_plan.instances
        }
        for source, child in walk_plan.edges:
            parents[child].append(source)
        record_of = {record.walk_id: record for record in walk_plan.walks}
        user_walk_of = {
            record.walk_id: walks.user_walk(record, walk_plan.walks)
            for record in walk_plan.walks
        }
        has_flights = any(record.flight_id is not None for record in walk_plan.walks)
        return _RunPlan(
            flow_dir=flow_dir,
            daedalus_root=daedalus_root,
            config=config,
            walk_plan=walk_plan,
            dir_of={
                inst.instance_id: _daedalus_dir(daedalus_root, inst)
                for inst in walk_plan.instances
            },
            parents_of={iid: tuple(sorted(ps)) for iid, ps in parents.items()},
            record_of=record_of,
            user_walk_of=user_walk_of,
            has_flights=has_flights,
            module_dir_of={step.module_id: step.module_dir for step in plan.steps},
            role_of={step.module_id: step.role for step in plan.steps},
        )

    @staticmethod
    def _dispatch(
        run: _RunPlan, state: _RunState, *, already_done: set[str] | None = None
    ) -> None:
        """Dispatch every instance over G* through the ready-set scheduler."""
        # The runner records each settled status and duration into state and
        # keeps the first failure. Instances in already_done (the emitter) return
        # their recorded status without re-running.
        from daedalus.core.engine import scheduler  # noqa: PLC0415 (lazy)

        done = already_done or set()
        by_id = {inst.instance_id: inst for inst in run.walk_plan.instances}

        def runner(instance_id: str) -> StepStatus:
            if instance_id in done:
                return StepStatus(state.module_status[instance_id])
            instance = by_id[instance_id]
            state.module_status[instance_id] = StepStatus.RUNNING.value
            outcome = _run_one_instance(run, instance)
            state.durations[instance_id] = outcome.duration_s
            state.started_at[instance_id] = outcome.manifest.started_at
            state.finished_at[instance_id] = outcome.manifest.finished_at
            state.module_status[instance_id] = outcome.manifest.status
            if outcome.error is not None:
                state.step_errors[instance_id] = outcome.error
                _record_error_code(state, instance_id, outcome.error_code)
            if outcome.error is not None and state.error is None:
                state.error = outcome.error
                state.missing_package = outcome.missing_package
            return outcome.status

        scheduler.run_instances(
            run.walk_plan, runner, max_workers=run.config.max_workers
        )

    def get_status(self, flow_id: str) -> FlowStatus:
        """Read ``dae-outputs/flows/<flow_id>`` from cwd into a FlowStatus.

        The output root is resolved from the current working directory (the
        user's current lab), matching how ``dae flow status`` runs.
        """
        flow_dir = Path("dae-outputs") / "flows" / flow_id
        record = lineage.read_flow_record(flow_dir)
        module_status = {step.step_id: step.status for step in record.steps}
        return FlowStatus(
            flow_id=record.flow_id,
            status=record.status,
            lab_name=record.lab_name,
            module_status=module_status,
            created_at=record.created_at,
        )

    def resume_flow(
        self, dag: nx.DiGraph, config: LabConfig, flow_id: str
    ) -> ExecutionResult:
        """Replay a failed flow's recorded plan, skipping its completed steps.

        The plan is re-derived so instance ids match the record. M comes from the
        recorded lineage rather than a rerun of the emitter. Completed instances
        keep their manifests and timings; the same ``flow_id`` is updated in place.
        """
        from daedalus.core import recipe, walks  # noqa: PLC0415

        plan: ExecutionPlan = dag
        spec = recipe.load_recipe(config.lab_dir / "lab.yaml")
        propagated = walks.propagate(spec, config.lab_dir)
        if isinstance(propagated, walks.WalkDefect):
            msg = (
                f"walks.propagate refused an already-validated lab: "
                f"{propagated.token} ({propagated.reason})"
            )
            raise RuntimeError(msg)

        flow_dir = config.output_root / "flows" / flow_id
        record = lineage.read_flow_record(flow_dir)

        # M comes from the recorded lineage (distinct flight ids), not from re-running
        # the emitter, so a non-deterministic emitter cannot change the resumed shape.
        flight_ids = {w.flight_id for w in record.walks if w.flight_id is not None}
        if len(flight_ids) > 1:
            from daedalus.core import flights  # noqa: PLC0415 (lazy, pulls networkx)

            propagated = flights.expand_flights(propagated, len(flight_ids))

        run = self._build_run_plan(flow_dir, config, propagated, plan)

        recorded = {step.step_id: step for step in record.steps}
        completed = {
            iid
            for iid, step in recorded.items()
            if step.status == StepStatus.COMPLETED.value
        }
        state = _RunState(
            flow_id=flow_id,
            flow_dir=flow_dir,
            config=config,
            created_at=record.created_at,
            walk_plan=propagated,
            module_status={
                inst.instance_id: (
                    StepStatus.COMPLETED.value
                    if inst.instance_id in completed
                    else StepStatus.SUBMITTED.value
                )
                for inst in propagated.instances
            },
            durations={},
            user_walk_of=run.user_walk_of,
        )
        # Carry the recorded timings of the completed steps so the rewritten flow
        # record keeps them (the dispatch short-circuits these, never re-timing).
        for iid in completed:
            step = recorded[iid]
            state.durations[iid] = (
                step.duration_s if step.duration_s is not None else 0.0
            )
            state.started_at[iid] = step.started_at
            state.finished_at[iid] = step.finished_at

        state.write_flow_record(StepStatus.RUNNING.value)
        self._dispatch(run, state, already_done=completed)

        flow_status = (
            StepStatus.FAILED.value
            if state.error is not None
            else StepStatus.COMPLETED.value
        )
        finished_at = datetime.now(UTC).isoformat()
        state.write_flow_record(flow_status)
        _finalize_outputs(run, flow_status)
        return ExecutionResult(
            flow_id=flow_id,
            status=flow_status,
            lab_name=config.lab_name,
            module_status=dict(state.module_status),
            started_at=state.created_at,
            finished_at=finished_at,
            error=state.error,
            missing_package=state.missing_package,
            empty_partition=False,
        )
