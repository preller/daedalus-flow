"""Unit tests for core/engine/scheduler.py and the derive_seed instance-id keying."""

from __future__ import annotations

import hashlib
import inspect

import pytest

pytestmark = pytest.mark.integration


def test_derive_seed_keys_on_instance_id() -> None:
    """derive_seed keys on instance_id with sha256; a bare module id still works."""
    from daedalus.core.engine.step import derive_seed

    # the second parameter is instance_id
    sig = inspect.signature(derive_seed)
    params = list(sig.parameters)
    assert params[1] == "instance_id", (
        f"derive_seed second param must be 'instance_id', got {params[1]!r}"
    )

    # two instance ids of the same module give distinct seeds
    seed_w2 = derive_seed(0, "some_module@w2")
    seed_w3 = derive_seed(0, "some_module@w3")
    assert seed_w2 != seed_w3, (
        "distinct instance ids must yield distinct seeds; got the same value"
    )

    # the same call twice gives the same result
    assert derive_seed(0, "some_module@w2") == seed_w2
    assert derive_seed(0, "some_module@w3") == seed_w3

    # sha256, never hash()
    def expected(flow_seed: int, instance_id: str) -> int:
        digest = hashlib.sha256(f"{flow_seed}:{instance_id}".encode()).digest()
        return int.from_bytes(digest[:4], "big")

    assert derive_seed(0, "some_module@w2") == expected(0, "some_module@w2")
    assert derive_seed(0, "some_module@w3") == expected(0, "some_module@w3")

    # the bare module form is unchanged
    assert derive_seed(0, "emit_ticks") == expected(0, "emit_ticks")
    assert derive_seed(42, "emit_ticks") == expected(42, "emit_ticks")


# The scheduler owns the instance states and the ready set, dispatches in
# lexicographic instance-id order and holds the collector barrier as its own
# state. A fake runner writes no files, so readiness never comes from disk.

from pathlib import Path  # noqa: E402
from typing import TYPE_CHECKING  # noqa: E402

if TYPE_CHECKING:
    from daedalus.core.engine.protocol import StepStatus
    from daedalus.core.walks import WalkPlan


def _diamond_join_plan(tmp_path: Path) -> WalkPlan:
    """Build the diamond_join WalkPlan inline; seed -> {left, right} -> join."""
    from daedalus.core.recipe import load_recipe_text
    from daedalus.core.walks import WalkPlan, propagate

    # seed sits on w1 with join; left mints w2 and right mints w3. The lexicographic
    # instance-id order is join@w1 < left@w2 < right@w3 < seed@w1.
    lab_dir = tmp_path / "lab"
    modules = [
        ("seed", [], "transform"),
        ("left", ["seed"], "transform"),
        ("right", ["seed"], "transform"),
        ("join", ["left", "right"], "walk_collector"),
    ]
    lines = ["name: inline", "modules:"]
    for module_id, depends, role in modules:
        lines.append(f"  - id: {module_id}")
        if depends:
            lines.append(f"    depends: [{', '.join(depends)}]")
        module_dir = lab_dir / "modules" / module_id
        module_dir.mkdir(parents=True)
        (module_dir / "dae-module.yaml").write_text(f"role: {role}\n")
    text = "\n".join(lines) + "\n"
    (lab_dir / "lab.yaml").write_text(text)
    plan = propagate(load_recipe_text(text), lab_dir)
    assert isinstance(plan, WalkPlan), f"expected a WalkPlan, got {plan!r}"
    return plan


class _RecordingRunner:
    """A fake step runner that records dispatch order and writes no files."""

    def __init__(self, fail: set[str] | None = None) -> None:
        self.dispatched: list[str] = []  # instance ids in dispatch order
        self._fail = fail or set()  # instance ids that resolve to FAILED

    def __call__(self, instance_id: str) -> StepStatus:
        from daedalus.core.engine.protocol import StepStatus

        self.dispatched.append(instance_id)
        if instance_id in self._fail:
            return StepStatus.FAILED
        return StepStatus.COMPLETED


def test_ready_set_dispatch_is_lexicographic_total_order_at_k1(
    tmp_path: Path,
) -> None:
    from daedalus.core.engine.scheduler import run_instances

    plan = _diamond_join_plan(tmp_path)

    orders: list[tuple[str, ...]] = []
    for _ in range(3):
        runner = _RecordingRunner()
        result = run_instances(plan, runner)
        orders.append(tuple(runner.dispatched))

    # seed@w1 is the only source; then left@w2 and right@w3 are simultaneously
    # ready and dispatched in lexicographic order; join@w1 only after both.
    assert orders[0] == ("seed@w1", "left@w2", "right@w3", "join@w1")
    # every run gives the identical order.
    assert orders[0] == orders[1] == orders[2]
    assert tuple(result.dispatch_order) == orders[0]


def test_siblings_are_simultaneously_ready(tmp_path: Path) -> None:
    """Neither sibling waits on the other; the lexicographic tie-break orders them."""
    from daedalus.core.engine.scheduler import run_instances

    plan = _diamond_join_plan(tmp_path)
    runner = _RecordingRunner()
    run_instances(plan, runner)

    # left dispatched strictly before right (lexicographic), and both strictly
    # before join (the collector barrier), and strictly after seed (the root).
    order = runner.dispatched
    assert order.index("seed@w1") < order.index("left@w2")
    assert order.index("left@w2") < order.index("right@w3")
    assert order.index("right@w3") < order.index("join@w1")


def test_collector_barrier_is_scheduler_state_not_files(tmp_path: Path) -> None:
    """join@w1 dispatches only after both parents completed, per scheduler state."""
    from daedalus.core.engine.protocol import StepStatus
    from daedalus.core.engine.scheduler import run_instances

    completed_at_dispatch: dict[str, frozenset[str]] = {}
    completed: set[str] = set()

    def runner(instance_id: str) -> StepStatus:
        completed_at_dispatch[instance_id] = frozenset(completed)
        completed.add(instance_id)
        return StepStatus.COMPLETED

    plan = _diamond_join_plan(tmp_path)
    run_instances(plan, runner)

    # When join@w1 was dispatched, both parents were already completed.
    assert {"left@w2", "right@w3"} <= completed_at_dispatch["join@w1"]
    # And neither sibling had the other as a precondition at its own dispatch.
    assert "right@w3" not in completed_at_dispatch["left@w2"]


def test_collector_not_dispatched_until_all_parents_complete(
    tmp_path: Path,
) -> None:
    """A failed left@w2 leaves join@w1 undispatched although right@w3 ran."""
    from daedalus.core.engine.protocol import StepStatus
    from daedalus.core.engine.scheduler import run_instances

    plan = _diamond_join_plan(tmp_path)
    runner = _RecordingRunner(fail={"left@w2"})
    result = run_instances(plan, runner)

    assert "join@w1" not in runner.dispatched
    assert result.statuses["join@w1"] == StepStatus.SUBMITTED


def test_failure_stops_dispatch_and_join_stays_submitted(
    tmp_path: Path,
) -> None:
    """left@w2 fails; seed stays completed, join stays submitted, failed is set."""
    from daedalus.core.engine.protocol import StepStatus
    from daedalus.core.engine.scheduler import run_instances

    plan = _diamond_join_plan(tmp_path)
    runner = _RecordingRunner(fail={"left@w2"})
    result = run_instances(plan, runner)

    assert result.statuses["seed@w1"] == StepStatus.COMPLETED
    assert result.statuses["left@w2"] == StepStatus.FAILED
    assert result.statuses["join@w1"] == StepStatus.SUBMITTED
    assert result.failed is True
    assert result.first_failure == "left@w2"


def test_max_workers_defaults_1_pools_above_1_and_rejects_below_1(
    tmp_path: Path,
) -> None:
    """K>1 keeps the K=1 dispatch order and settles each instance once; K<1 raises."""
    import inspect

    from daedalus.core.engine.protocol import StepStatus
    from daedalus.core.engine.scheduler import run_instances

    sig = inspect.signature(run_instances)
    assert sig.parameters["max_workers"].default == 1

    plan = _diamond_join_plan(tmp_path)
    all_ids = {inst.instance_id for inst in plan.instances}

    # K=1, the serial total order; every instance settles completed exactly once.
    r1 = run_instances(plan, _RecordingRunner())
    assert set(r1.statuses) == all_ids
    assert all(s is StepStatus.COMPLETED for s in r1.statuses.values())

    # K=4 runs a bounded pool that still settles every instance once.
    runner4 = _RecordingRunner()
    r4 = run_instances(plan, runner4, max_workers=4)
    assert set(runner4.dispatched) == all_ids
    assert all(s is StepStatus.COMPLETED for s in r4.statuses.values())

    # The dispatch order is identical across K>1 runs and equals the K=1 total order;
    # the single scheduler thread records each wave in sorted order.
    r4b = run_instances(plan, _RecordingRunner(), max_workers=4)
    assert r4.dispatch_order == r4b.dispatch_order == r1.dispatch_order

    import pytest

    for bad in (0, -1):
        with pytest.raises(ValueError, match="positive integer"):
            run_instances(plan, _RecordingRunner(), max_workers=bad)


def test_walk_inputs_resolved_walk_id_to_tail_dir(tmp_path: Path) -> None:
    """join@w1's walk_inputs map walk id to tail dir in sorted walk-id order."""
    from daedalus.core.engine.scheduler import resolve_walk_inputs

    plan = _diamond_join_plan(tmp_path)

    def dir_of(instance_id: str) -> str:
        return f"/runs/{instance_id}"

    resolved = resolve_walk_inputs(plan, "join@w1", dir_of)
    assert resolved == {"w2": "/runs/left@w2", "w3": "/runs/right@w3"}
    # Key order is sorted walk-id order, not insertion or completion order.
    assert list(resolved) == ["w2", "w3"]
