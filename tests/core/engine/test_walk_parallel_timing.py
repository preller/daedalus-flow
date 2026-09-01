"""Walk-level parallelism as read from ``dae --json flow status``.

The ``parallel`` example at K=4 shows branch order, the combine barrier and overlap.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from tests._helpers import copy_parallel_example, run_cli_json

pytestmark = pytest.mark.slow

BRANCHES = frozenset({"stat_sum", "stat_max", "stat_min", "stat_mean"})
SPLIT = "split"
COMBINE = "combine"
WIDTH = len(BRANCHES)


@pytest.fixture(autouse=True)
def _prefect_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Ephemeral, quiet Prefect settings, set before the engine imports prefect."""
    home = tmp_path / "prefect_home"
    home.mkdir()
    monkeypatch.setenv("PREFECT_SERVER_ALLOW_EPHEMERAL_MODE", "true")
    monkeypatch.setenv("PREFECT_LOGGING_LEVEL", "CRITICAL")
    monkeypatch.setenv("PREFECT_LOGGING_TO_API_ENABLED", "false")
    monkeypatch.setenv("PREFECT_SERVER_ANALYTICS_ENABLED", "false")
    monkeypatch.setenv("PREFECT_HOME", str(home))


def _module(step_id: str) -> str:
    """The module id of an instance id (``stat_max@w2`` -> ``stat_max``)."""
    return step_id.split("@", 1)[0]


def _ts(value: str) -> float:
    """Epoch seconds of a timestamp from the --json contract."""
    return datetime.fromisoformat(value).timestamp()


def _steps_by_module(lab: Path) -> dict[str, dict[str, float]]:
    """Run the lab, then read flow status into {module: {start, finish}}."""
    run = run_cli_json(lab, "lab", "run")
    assert run["code"] == "dae.lab.run.ok", run
    status = run_cli_json(lab, "flow", "status")
    assert status["code"] == "dae.flow.status.ok", status
    out: dict[str, dict[str, float]] = {}
    for step in status["data"]["steps"]:
        assert step["started_at"] is not None, f"no started_at on {step['id']}"
        assert step["finished_at"] is not None, f"no finished_at on {step['id']}"
        out[_module(step["id"])] = {
            "start": _ts(step["started_at"]),
            "finish": _ts(step["finished_at"]),
        }
    return out


def _max_concurrency(intervals: list[tuple[float, float]]) -> int:
    """Most intervals open at one instant; intervals that only touch do not count."""
    events: list[tuple[float, int]] = []
    for start, finish in intervals:
        events.append((start, 1))
        events.append((finish, -1))
    events.sort(key=lambda e: (e[0], e[1]))  # -1 before +1 at equal ts -> strict
    current = best = 0
    for _, delta in events:
        current += delta
        best = max(best, current)
    return best


@pytest.mark.parametrize("engine", ["local", "prefect"])
def test_parallel_order_and_barrier_hold(tmp_path: Path, engine: str) -> None:
    """Holds on a serial engine too; this pins order, not parallelism."""
    if engine == "prefect":
        pytest.importorskip(
            "prefect", reason="the optional daedalus-flow[engine] extra"
        )
    lab = copy_parallel_example(tmp_path, engine=engine, max_workers=WIDTH)
    steps = _steps_by_module(lab)

    assert set(steps) >= BRANCHES, f"missing branch steps: {BRANCHES - set(steps)}"
    split_finish = steps[SPLIT]["finish"]
    # Every branch starts only after split (its single G* parent) finishes.
    for branch in BRANCHES:
        assert steps[branch]["start"] >= split_finish, (
            f"{branch} started before split finished ({engine})"
        )
    # combine starts only after the last branch finishes.
    last_branch_finish = max(steps[branch]["finish"] for branch in BRANCHES)
    assert steps[COMBINE]["start"] >= last_branch_finish, (
        f"combine started before all branches finished ({engine})"
    )


@pytest.mark.parametrize("engine", ["local", "prefect"])
def test_parallel_branches_overlap_at_capacity(tmp_path: Path, engine: str) -> None:
    """At max_workers == width at least two branches overlap in wall-clock time."""
    if engine == "prefect":
        pytest.importorskip(
            "prefect", reason="the optional daedalus-flow[engine] extra"
        )
    lab = copy_parallel_example(tmp_path, engine=engine, max_workers=WIDTH)
    steps = _steps_by_module(lab)

    branch_intervals = [
        (steps[branch]["start"], steps[branch]["finish"]) for branch in BRANCHES
    ]
    observed = _max_concurrency(branch_intervals)
    # >= 2, not == WIDTH: the intervals include each branch's uv spin-up, so on a
    # busy box the launches may stagger enough that a strict 4 reads 3. Serial
    # execution yields exactly 1.
    assert observed >= 2, (
        f"{engine}: observed branch concurrency {observed}, expected >= 2 "
        f"(serial execution ignores max_workers and yields 1)"
    )
