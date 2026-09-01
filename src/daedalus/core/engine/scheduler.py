"""The G* ready-set dispatcher over a propagated WalkPlan.

The scheduler tracks per-instance states, computes the ready set and calls a
``runner`` per instance; it touches neither the filesystem nor the clock. An
instance is ready once every G* parent is COMPLETED in the scheduler's own
table. The ready set dispatches in lexicographic order, so the order is the
same on every run. ``max_workers == 1`` runs instances in-process one at a time;
``max_workers > 1`` runs waves of at most K fresh subprocesses.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from daedalus.core.engine.protocol import StepStatus

if TYPE_CHECKING:
    from daedalus.core.walks import WalkPlan

# The runner executes one instance and returns its settled status, COMPLETED
# or FAILED; SUBMITTED and RUNNING are scheduler-internal states.
Runner = Callable[[str], StepStatus]


def resolve_walk_inputs(
    walk_plan: WalkPlan,
    collector_instance: str,
    dir_of: Callable[[str], str],
) -> dict[str, str]:
    """Resolve a collector's walk_inputs from walk id to its tail-instance dir.

    ``walk_plan.walk_inputs[collector_instance]`` maps each child walk id to its
    tail instance id and ``dir_of`` maps an instance id to its directory. The result
    iterates in sorted walk-id order, a stable key order rather than completion order.
    """
    plan = walk_plan.walk_inputs[collector_instance]
    return {walk_id: dir_of(plan[walk_id]) for walk_id in sorted(plan)}


@dataclass(frozen=True)
class SchedulerResult:
    """The settled outcome of one scheduler pass over a WalkPlan."""

    statuses: Mapping[str, StepStatus]  # final state table, keyed by instance id
    dispatch_order: tuple[str, ...]  # the lexicographic dispatch sequence
    first_failure: str | None = None  # lexicographically first FAILED instance

    @property
    def failed(self) -> bool:
        """True iff any dispatched instance settled to FAILED."""
        return self.first_failure is not None


@dataclass
class _State:
    """Mutable scheduler state for one pass (the single-writer table)."""

    parents: dict[str, frozenset[str]]
    status: dict[str, StepStatus]
    order: list[str] = field(default_factory=list)

    def is_ready(self, instance: str) -> bool:
        """True iff still SUBMITTED and every G* parent is COMPLETED."""
        if self.status[instance] is not StepStatus.SUBMITTED:
            return False
        return all(
            self.status[parent] is StepStatus.COMPLETED
            for parent in self.parents[instance]
        )

    def ready_set(self) -> list[str]:
        """The lexicographically-sorted ids of all currently ready instances."""
        return sorted(i for i in self.status if self.is_ready(i))


def run_instances(
    walk_plan: WalkPlan,
    runner: Runner,
    *,
    max_workers: int = 1,
) -> SchedulerResult:
    """Dispatch every instance of ``walk_plan`` over its G* edges.

    Each instance starts SUBMITTED; the smallest ready instances dispatch through
    ``runner`` and take the status it returns, until none is ready. Instances whose
    parents never completed stay SUBMITTED. ``max_workers < 1`` is a ValueError.
    """
    if max_workers < 1:
        msg = f"max_workers must be a positive integer, got {max_workers}."
        raise ValueError(msg)

    parents: dict[str, frozenset[str]] = {
        inst.instance_id: frozenset() for inst in walk_plan.instances
    }
    grouped: dict[str, set[str]] = {key: set() for key in parents}
    for parent, child in walk_plan.edges:
        grouped[child].add(parent)
    parents = {child: frozenset(ps) for child, ps in grouped.items()}

    state = _State(
        parents=parents,
        status={inst.instance_id: StepStatus.SUBMITTED for inst in walk_plan.instances},
    )

    # K=1 dispatches one ready instance at a time, recomputing readiness after
    # each settle; K>1 runs bounded waves over fresh subprocesses. Both keep the
    # scheduler the sole writer of the state table.
    if max_workers == 1:
        while True:
            ready = state.ready_set()
            if not ready:
                break
            instance = ready[0]
            settled = runner(instance)
            state.status[instance] = settled
            state.order.append(instance)
    else:
        _run_bounded_waves(state, runner, max_workers)

    first_failure = next(
        (i for i in sorted(state.status) if state.status[i] is StepStatus.FAILED),
        None,
    )
    return SchedulerResult(
        statuses=dict(state.status),
        dispatch_order=tuple(state.order),
        first_failure=first_failure,
    )


def _run_bounded_waves(state: _State, runner: Runner, max_workers: int) -> None:
    """Dispatch ready instances in deterministic waves of at most ``max_workers``."""
    # Each wave submits the smallest ready instances to a pool whose runner
    # launches a fresh child per instance, then drains every future before
    # recomputing readiness. The scheduler thread records statuses in sorted order.
    from concurrent.futures import ThreadPoolExecutor  # noqa: PLC0415 (lazy)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        while True:
            ready = state.ready_set()
            if not ready:
                break
            # ``ready`` is already lexicographically sorted; cap the wave at K.
            wave = ready[:max_workers]
            futures = {instance: pool.submit(runner, instance) for instance in wave}
            # Drain the whole wave, then write the state table in sorted order
            # rather than completion order.
            for instance in wave:
                state.status[instance] = futures[instance].result()
                state.order.append(instance)
