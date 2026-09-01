"""The optional Prefect v3 engine, selected by ``engine: prefect``.

:class:`PrefectEngine` subclasses :class:`LocalEngine` and overrides only the
dispatch. Every post-emitter instance becomes a Prefect task submitted with
``wait_for`` on its G* parents, under a ``ThreadPoolTaskRunner(max_workers=K)``.
Isolation stays the subprocess shim's job, so the lineage matches a local run.
Only the CLI engine selector imports this module, and ``prefect`` itself is
imported inside ``_dispatch``; the ``daedalus-flow[engine]`` extra provides it.
"""

from __future__ import annotations

import itertools
import os
import time
from typing import TYPE_CHECKING, Any

from daedalus.core.engine.local import LocalEngine, _run_one_instance
from daedalus.core.engine.subprocess_runner import read_step_log_tail

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from daedalus.core.engine.local import _RunPlan, _RunState, _StepOutcome


class _PrefectInstanceFailed(Exception):  # noqa: N818 (engine-internal control signal)
    """Raised inside a Prefect task when its module failed; carries the outcome."""

    def __init__(self, outcome: _StepOutcome) -> None:
        super().__init__(outcome.error or "instance failed")
        self.outcome = outcome


def _make_progress_counter() -> Callable[[], int]:
    """A thread-safe ``1, 2, 3, ...`` tally for the ``(k/N)`` progress lines."""
    # itertools.count(1).__next__ is one C call, atomic under the interpreter
    # lock, so concurrent callers get distinct, gap-free integers.
    return itertools.count(1).__next__


def _log_failure_tail(logger: Any, instance_id: str, step_dir: Path) -> None:
    """Log the tail of a failed step's ``step.log``, when there is one."""
    tail = read_step_log_tail(step_dir)
    if tail:
        logger.error(f"Last output from {instance_id} before it failed:\n{tail}")


def _topological_order(run: _RunPlan, done: set[str]) -> list[str]:
    """Topological order of the instances outside ``done``, sorted within a layer."""
    # A parent's future then exists before its child is submitted, and the
    # submission order is the same on every run.
    pending = sorted(
        inst.instance_id
        for inst in run.walk_plan.instances
        if inst.instance_id not in done
    )
    satisfied = set(done)
    order: list[str] = []
    while pending:
        ready = [
            iid
            for iid in pending
            if all(p in satisfied for p in run.parents_of.get(iid, ()))
        ]
        if not ready:
            # Unsatisfiable remainder (a cycle or a parent outside the plan, both
            # ruled out by validation upstream); append deterministically so the run
            # terminates rather than spinning.
            order.extend(pending)
            break
        order.extend(ready)
        satisfied.update(ready)
        pending = [iid for iid in pending if iid not in satisfied]
    return order


def _submit_dag(run_instance: Any, run: _RunPlan, order: list[str]) -> dict[str, Any]:
    """Submit each instance in ``order``, waiting on its G* parents' futures."""
    # Pre-run parents (the emitter) are absent from futures and already on disk.
    futures: dict[str, Any] = {}
    for instance_id in order:
        upstream = [
            futures[parent]
            for parent in run.parents_of.get(instance_id, ())
            if parent in futures
        ]
        futures[instance_id] = run_instance.submit(instance_id, wait_for=upstream)
    return futures


def _record_outcome(state: _RunState, instance_id: str, outcome: _StepOutcome) -> None:
    """Write one settled instance's status and timing into ``state``."""
    # The main thread is the single writer of state; tasks only return outcomes.
    state.durations[instance_id] = outcome.duration_s
    state.started_at[instance_id] = outcome.manifest.started_at
    state.finished_at[instance_id] = outcome.manifest.finished_at
    state.module_status[instance_id] = outcome.manifest.status
    if outcome.error is not None and state.error is None:
        state.error = outcome.error
        state.missing_package = outcome.missing_package


def _settle_one(state: _RunState, instance_id: str, future: Any) -> None:
    """Record one settled future into ``state``, matching LocalEngine's terminals."""
    # A completed task returns its outcome; a failed one re-raises the carried
    # outcome. Anything else never ran because an ancestor failed, and keeps
    # its SUBMITTED status.
    prefect_state = future.state
    if prefect_state.is_completed():
        _record_outcome(state, instance_id, future.result())
        return
    if not prefect_state.is_failed():
        return
    try:
        future.result(raise_on_failure=True)
    except _PrefectInstanceFailed as failure:
        _record_outcome(state, instance_id, failure.outcome)
    except Exception as unexpected:  # noqa: BLE001 (engine must not crash on an unmodeled task error)
        _record_unexpected_failure(state, instance_id, unexpected)


def _record_unexpected_failure(
    state: _RunState, instance_id: str, error: BaseException
) -> None:
    """Record an instance that died with an unmodeled exception as FAILED."""
    # A provisioning crash or a bug before _run_one_instance wraps the error would
    # otherwise escape run_lab as a raw traceback and bypass the lineage writer.
    # No manifest exists, so timing stays absent; the first failure wins.
    from daedalus.core.engine.protocol import StepStatus  # noqa: PLC0415 (lazy import)

    state.module_status[instance_id] = StepStatus.FAILED.value
    state.durations.setdefault(instance_id, 0.0)
    if state.error is None:
        state.error = str(error) or error.__class__.__name__


def _settle(state: _RunState, futures: dict[str, Any]) -> None:
    """Record every settled future into ``state`` in sorted instance-id order."""
    for instance_id in sorted(futures):
        _settle_one(state, instance_id, futures[instance_id])


def _silence_upstream_pydantic_warning() -> None:
    """Ignore one pydantic warning Prefect triggers, here and in its server child."""
    import warnings  # noqa: PLC0415 (lazy, prefect path only)

    # The filter is by message, not category; a category rule in `PYTHONWARNINGS`
    # fails at child start because the third-party class is not importable that
    # early. If Prefect rewords the message the line reappears, harmlessly.
    message = "The 'deprecated' attribute with value True was provided"
    warnings.filterwarnings("ignore", message=message)
    rule = f"ignore:{message}"
    current = os.environ.get("PYTHONWARNINGS", "")
    if rule not in current:
        os.environ["PYTHONWARNINGS"] = f"{current},{rule}" if current else rule


class PrefectEngine(LocalEngine):
    """Run a lab under Prefect v3, reusing LocalEngine's lineage machinery."""

    @staticmethod
    def _dispatch(
        run: _RunPlan, state: _RunState, *, already_done: set[str] | None = None
    ) -> None:
        """Dispatch every post-emitter instance as a Prefect task in one flow."""
        # Ephemeral in-process mode, with Prefect's own logging and telemetry quiet
        # so they stay off the stdout --json contract. Set before importing
        # prefect; setdefault lets a caller override (a `PREFECT_API_URL`, a level).
        os.environ.setdefault("PREFECT_SERVER_ALLOW_EPHEMERAL_MODE", "true")
        os.environ.setdefault("DO_NOT_TRACK", "1")
        os.environ.setdefault("PREFECT_SERVER_ANALYTICS_ENABLED", "false")
        os.environ.setdefault("PREFECT_LOGGING_TO_API_ENABLED", "false")
        os.environ.setdefault("PREFECT_LOGGING_LEVEL", "INFO")
        # Drop one upstream-only pydantic warning before the import. See the helper.
        _silence_upstream_pydantic_warning()
        import prefect  # noqa: PLC0415 (lazy: the optional [engine] extra, cold 1-3s)
        from prefect import get_run_logger  # noqa: PLC0415 (lazy)
        from prefect.futures import wait  # noqa: PLC0415 (lazy)
        from prefect.task_runners import ThreadPoolTaskRunner  # noqa: PLC0415 (lazy)

        # Prefect enforces order and the collector barrier through wait_for, and
        # the ThreadPoolTaskRunner caps concurrency at K. already_done (the pre-run
        # emitter) is not submitted; its descendants just omit it from wait_for.
        done = already_done or set()
        by_id = {inst.instance_id: inst for inst in run.walk_plan.instances}
        order = _topological_order(run, done)
        # total is the number of submitted instances (the emitter in done already
        # ran); next_completed stamps each settled step's k in (k/N). The extra
        # lines go through Prefect's run logger, so they interleave with its own.
        total = len(order)
        next_completed = _make_progress_counter()

        @prefect.task(persist_result=False, task_run_name="{instance_id}")
        def run_instance(instance_id: str) -> _StepOutcome:
            """Run one instance through the core runner LocalEngine uses.

            Logs a Starting line, then Finished or Failed with the elapsed time and
            a running k/N. A failure raises so Prefect leaves the ``wait_for``
            descendants un-run, with the outcome riding the exception.
            """
            logger = get_run_logger()
            logger.info(f"Starting {instance_id}")
            outcome = _run_one_instance(run, by_id[instance_id])
            tally = f"{outcome.duration_s:.2f}s ({next_completed()}/{total})"
            if outcome.error is not None:
                logger.info(f"Failed {instance_id} in {tally}")
                _log_failure_tail(logger, instance_id, run.dir_of[instance_id])
                raise _PrefectInstanceFailed(outcome)
            logger.info(f"Finished {instance_id} in {tally}")
            return outcome

        # Annotated Any because Prefect's runner generic resolves to Never here,
        # which the flow decorator's TaskRunner[PrefectFuture[Any]] bound rejects.
        task_runner: Any = ThreadPoolTaskRunner(max_workers=run.config.max_workers)

        @prefect.flow(name=run.config.lab_name, task_runner=task_runner)
        def run_lab() -> None:
            logger = get_run_logger()
            started = time.monotonic()
            futures = _submit_dag(run_instance, run, order)
            if futures:
                wait(list(futures.values()))
            _settle(state, futures)
            # One wall-clock summary on the flow-run logger, after every per-step
            # line. A step that never reached its body (an ancestor failed) has no
            # per-step line, so the count shows a partial run as partial.
            wall = time.monotonic() - started
            logger.info(f"Lab finished: {total} steps in {wall:.2f}s")

        run_lab()
