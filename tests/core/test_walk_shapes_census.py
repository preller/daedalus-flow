"""Per-shape census and join tests, read directly off walks.propagate.

Shared goldens and helpers live in tests/core/_walk_shapes.py.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from tests.core._walk_shapes import _branch_walks, _copy_lab, _plan, _run_cli_in

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.integration  # validates and runs the engine over 23 shapes


def test_wide_join_walk_inputs_are_stable_keyed_in_order() -> None:
    """Keys are the internal walk ids, sorted, mapped to the branch tails."""
    for name, width in (("wide4_join", 4), ("wide5_join", 5)):
        plan = _plan(name)
        (collector,) = plan.terminal
        inputs = plan.walk_inputs[collector]
        assert len(inputs) == width
        assert list(inputs) == sorted(inputs)
        # Each value is a distinct branch tail instance (module@walk).
        assert len({v for v in inputs.values()}) == width


def test_asym_join_walk_inputs_map_to_tails_not_born_at() -> None:
    """The long branch maps to slow_c (depth 3), not to its born-at slow_a."""
    plan = _plan("asym_join")
    (collector,) = plan.terminal
    tails = {v.split("@")[0] for v in plan.walk_inputs[collector].values()}
    assert tails == {"quick", "slow_c"}


def test_nested_join_each_collector_closes_one_level() -> None:
    """sub_join closes the inner group, top_join the outer; w4.parent == w2."""
    plan = _plan("nested_join")
    by_id = {r.walk_id: r for r in plan.walks}
    # The inner walks (w4, w5) are parented at the mid-branch walk (w2).
    assert by_id["w4"].parent_walk == "w2"
    assert by_id["w5"].parent_walk == "w2"
    # Two collectors, each over exactly one level's group.
    assert set(plan.walk_inputs) == {"sub_join@w2", "top_join@w1"}
    assert set(plan.walk_inputs["sub_join@w2"]) == {"w4", "w5"}
    assert set(plan.walk_inputs["top_join@w1"]) == {"w2", "w3"}


def test_series_diamonds_walk_count_adds_never_multiplies() -> None:
    """The first diamond is collected before mid fires, so the count is 2 + 2."""
    plan = _plan("series_diamonds")
    branches = _branch_walks(plan)
    assert len(branches) == 4
    assert all(r.parent_walk == "w1" for r in branches)


# --- terminal-walk fixtures and sibling_collectors


def _run_flow(name: str, tmp_path: Path) -> Path:
    """Copy, run, and return the single flow dir (asserting lab.run.ok)."""
    copy = _copy_lab(name, tmp_path)
    assert _run_cli_in(copy, "lab", "run") == (0, "dae.lab.run.ok")
    return next((copy / "dae-outputs" / "flows").iterdir())


def test_sibling_collectors_census_is_six_not_eight() -> None:
    """Root, flight root and four fits; the three collectors share w2 and one map."""
    plan = _plan("sibling_collectors")
    assert len(_branch_walks(plan)) == 4
    assert len(plan.walks) == 6  # w1 root + w2 flight-root + four fit walks
    collectors = {"coll_a@w2", "coll_b@w2", "coll_c@w2"}
    assert collectors <= set(plan.walk_inputs)
    maps = [dict(plan.walk_inputs[c]) for c in sorted(collectors)]
    assert all(m == maps[0] for m in maps)
    assert len(maps[0]) == 4


def test_sibling_collectors_dispatch_order_is_lexicographic(tmp_path: Path) -> None:
    """Read from the lineage steps[] order, not wall clocks."""
    flow = _run_flow("sibling_collectors", tmp_path)
    steps = json.loads((flow / "dae-flow.json").read_text())["steps"]
    order = [s["step_id"] for s in steps]
    idx = [order.index(f"coll_{x}@w2") for x in ("a", "b", "c")]
    assert idx == sorted(idx)


def test_mixed_collect_inner_collected_outer_uncollected() -> None:
    """sub_join closes the inner group; side@w3 runs uncollected to its terminal."""
    plan = _plan("mixed_collect")
    assert dict(plan.walk_inputs) == {
        "sub_join@w2": {"w4": "sub_a@w4", "w5": "sub_b@w5"}
    }
    assert "side@w3" in plan.terminal
