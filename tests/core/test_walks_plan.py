"""Direct coverage of configurations(), _config_lines() and the full G* plan shape.

Pure propagate pass over inline labs, exact-value assertions, stdlib fixtures only.
"""

from __future__ import annotations

from pathlib import Path

from tests.core._walks_helpers import _make_lab, _propagate_inline


def _iid(module: str, walk: str) -> str:
    """Instance id built from the engine's separator, not a literal '@'."""
    from daedalus.core.walks import _RESERVED_SEPARATOR

    return f"{module}{_RESERVED_SEPARATOR}{walk}"


def test_configurations_linear_is_single_source_to_sink_path(tmp_path: Path) -> None:
    """A linear lab has exactly one configuration walk, in source-to-sink order."""
    from daedalus.core.walks import WalkPlan, configurations

    plan = _propagate_inline(
        tmp_path / "linear",
        [
            ("seed", [], "transform"),
            ("a", ["seed"], "transform"),
            ("b", ["a"], "transform"),
        ],
    )
    assert isinstance(plan, WalkPlan)
    module_of = {i.instance_id: i.module_id for i in plan.instances}
    paths = configurations(plan)
    assert len(paths) == 1
    assert [module_of[iid] for iid in paths[0]] == ["seed", "a", "b"]


def test_configurations_fork_yields_one_path_per_branch_in_index_order(
    tmp_path: Path,
) -> None:
    from daedalus.core.walks import WalkPlan, configurations

    plan = _propagate_inline(
        tmp_path / "fork",
        [
            ("seed", [], "transform"),
            ("left", ["seed"], "transform"),
            ("right", ["seed"], "transform"),
        ],
    )
    assert isinstance(plan, WalkPlan)
    module_of = {i.instance_id: i.module_id for i in plan.instances}
    paths = configurations(plan)
    assert [[module_of[iid] for iid in p] for p in paths] == [
        ["seed", "left"],
        ["seed", "right"],
    ]


def test_triple_branch_collector_full_plan_structure(tmp_path: Path) -> None:
    """Ids, indices, edges, terminal, merge map, Full shape and configuration paths."""
    from daedalus.core.walks import WalkPlan, configurations
    from daedalus.flow import Role

    plan = _propagate_inline(
        tmp_path / "triple",
        [
            ("seed", [], Role.TRANSFORM),
            ("a", ["seed"], Role.TRANSFORM),
            ("b", ["seed"], Role.TRANSFORM),
            ("c", ["seed"], Role.TRANSFORM),
            ("join", ["a", "b", "c"], Role.WALK_COLLECTOR),
        ],
    )
    assert isinstance(plan, WalkPlan)
    assert [(i.instance_id, i.index, i.module_id) for i in plan.instances] == [
        (_iid("seed", "w1"), 1, "seed"),
        (_iid("a", "w2"), 2, "a"),
        (_iid("b", "w3"), 3, "b"),
        (_iid("c", "w4"), 4, "c"),
        (_iid("join", "w1"), 5, "join"),
    ]
    assert tuple(plan.edges) == (
        (_iid("a", "w2"), _iid("join", "w1")),
        (_iid("b", "w3"), _iid("join", "w1")),
        (_iid("c", "w4"), _iid("join", "w1")),
        (_iid("seed", "w1"), _iid("a", "w2")),
        (_iid("seed", "w1"), _iid("b", "w3")),
        (_iid("seed", "w1"), _iid("c", "w4")),
    )
    assert tuple(plan.terminal) == (_iid("join", "w1"),)
    assert {k: dict(v) for k, v in plan.walk_inputs.items()} == {
        _iid("join", "w1"): {
            "w2": _iid("a", "w2"),
            "w3": _iid("b", "w3"),
            "w4": _iid("c", "w4"),
        },
    }
    assert plan.config_full == "1-{2,3,4}-(5)"
    # one configuration per branch, in plan-index order (a flipped successor
    # sort or dropped source ordering in configurations() would reorder these):
    module_of = {i.instance_id: i.module_id for i in plan.instances}
    assert [[module_of[iid] for iid in path] for path in configurations(plan)] == [
        ["seed", "a", "join"],
        ["seed", "b", "join"],
        ["seed", "c", "join"],
    ]


def test_diamond_tail_broadcast_through_collector_full_structure(
    tmp_path: Path,
) -> None:
    """tail runs on w1 after the collector, so the root token is a broadcast prefix."""
    from daedalus.core.walks import WalkPlan
    from daedalus.flow import Role

    plan = _propagate_inline(
        tmp_path / "diamond_tail",
        [
            ("seed", [], Role.TRANSFORM),
            ("left", ["seed"], Role.TRANSFORM),
            ("right", ["seed"], Role.TRANSFORM),
            ("join", ["left", "right"], Role.WALK_COLLECTOR),
            ("tail", ["join"], Role.TRANSFORM),
        ],
    )
    assert isinstance(plan, WalkPlan)
    assert [(i.instance_id, i.index, i.module_id) for i in plan.instances] == [
        (_iid("seed", "w1"), 1, "seed"),
        (_iid("left", "w2"), 2, "left"),
        (_iid("right", "w3"), 3, "right"),
        (_iid("join", "w1"), 4, "join"),
        (_iid("tail", "w1"), 5, "tail"),
    ]
    assert tuple(plan.edges) == (
        (_iid("join", "w1"), _iid("tail", "w1")),
        (_iid("left", "w2"), _iid("join", "w1")),
        (_iid("right", "w3"), _iid("join", "w1")),
        (_iid("seed", "w1"), _iid("left", "w2")),
        (_iid("seed", "w1"), _iid("right", "w3")),
    )
    assert tuple(plan.terminal) == (_iid("tail", "w1"),)
    assert {k: dict(v) for k, v in plan.walk_inputs.items()} == {
        _iid("join", "w1"): {"w2": _iid("left", "w2"), "w3": _iid("right", "w3")},
    }
    assert plan.config_full == "1-{2,3}-(4)-5"


def test_walk_collector_with_ancestor_broadcast_input_full_structure(
    tmp_path: Path,
) -> None:
    """join reads brancher directly; the root walk feeds join@w1 beside the tails."""
    from daedalus.core.walks import WalkPlan
    from daedalus.flow import Role

    plan = _propagate_inline(
        tmp_path / "broadcast",
        [
            ("brancher", [], Role.TRANSFORM),
            ("left", ["brancher"], Role.TRANSFORM),
            ("right", ["brancher"], Role.TRANSFORM),
            ("join", ["brancher", "left", "right"], Role.WALK_COLLECTOR),
        ],
    )
    assert isinstance(plan, WalkPlan)
    assert [(i.instance_id, i.index, i.module_id) for i in plan.instances] == [
        (_iid("brancher", "w1"), 1, "brancher"),
        (_iid("left", "w2"), 2, "left"),
        (_iid("right", "w3"), 3, "right"),
        (_iid("join", "w1"), 4, "join"),
    ]
    # The broadcast edge brancher@w1 -> join@w1 is the regression target: it is
    # the ancestor-token parent feeding the collector instance.
    assert tuple(plan.edges) == (
        (_iid("brancher", "w1"), _iid("join", "w1")),
        (_iid("brancher", "w1"), _iid("left", "w2")),
        (_iid("brancher", "w1"), _iid("right", "w3")),
        (_iid("left", "w2"), _iid("join", "w1")),
        (_iid("right", "w3"), _iid("join", "w1")),
    )
    assert tuple(plan.terminal) == (_iid("join", "w1"),)
    assert {k: dict(v) for k, v in plan.walk_inputs.items()} == {
        _iid("join", "w1"): {"w2": _iid("left", "w2"), "w3": _iid("right", "w3")},
    }


def test_flight_collector_root_scope_edges_and_roles(tmp_path: Path) -> None:
    """sink sits on w1; mid@w2 -> sink@w1 is the root-scope edge. Roles kept."""
    from daedalus.core.walks import WalkPlan
    from daedalus.flow import Role

    plan = _propagate_inline(
        tmp_path / "flight",
        [
            ("source", [], Role.EMITTER),
            ("mid", ["source"], Role.TRANSFORM),
            ("sink", ["mid"], Role.FLIGHT_COLLECTOR),
        ],
    )
    assert isinstance(plan, WalkPlan)
    assert [(i.instance_id, i.index, i.module_id) for i in plan.instances] == [
        (_iid("source", "w1"), 1, "source"),
        (_iid("mid", "w2"), 2, "mid"),
        (_iid("sink", "w1"), 3, "sink"),
    ]
    assert tuple(plan.edges) == (
        (_iid("mid", "w2"), _iid("sink", "w1")),
        (_iid("source", "w1"), _iid("mid", "w2")),
    )
    assert tuple(plan.terminal) == (_iid("sink", "w1"),)
    assert dict(plan.roles) == {
        "source": Role.EMITTER.value,
        "mid": Role.TRANSFORM.value,
        "sink": Role.FLIGHT_COLLECTOR.value,
    }


def test_walks_and_replicated_instances_order_numerically_past_ten(
    tmp_path: Path,
) -> None:
    """A nine-way fan mints w2..w10; a string sort would place w10 before w2."""
    from daedalus.core.walks import WalkPlan
    from daedalus.flow import Role

    fan = [(f"s{i}", ["root"], Role.TRANSFORM) for i in range(1, 10)]
    plan = _propagate_inline(
        tmp_path / "wide",
        [
            ("root", [], Role.TRANSFORM),
            *fan,
            # ``tail`` reads the first and last fan branches: incomparable
            # sibling tokens w2 and w10, so it replicates onto both.
            ("tail", ["s1", "s9"], Role.TRANSFORM),
        ],
    )
    assert isinstance(plan, WalkPlan)
    assert [w.walk_id for w in plan.walks] == [f"w{i}" for i in range(1, 11)]
    assert [i.instance_id for i in plan.instances if i.module_id == "tail"] == [
        _iid("tail", "w2"),
        _iid("tail", "w10"),
    ]


def test_multi_group_collector_instances_order_by_parent_walk_numerically(
    tmp_path: Path,
) -> None:
    """Two complete groups on w2 and w10 give two instances, w2 before w10."""
    from daedalus.core.walks import WalkPlan
    from daedalus.flow import Role

    fan = [(f"s{i}", ["root"], Role.TRANSFORM) for i in range(1, 10)]
    plan = _propagate_inline(
        tmp_path / "multigroup",
        [
            ("root", [], Role.TRANSFORM),
            *fan,
            # s1 (walk w2) and s9 (walk w10) each fork into a complete pair.
            ("a1", ["s1"], Role.TRANSFORM),
            ("a2", ["s1"], Role.TRANSFORM),
            ("a3", ["s9"], Role.TRANSFORM),
            ("a4", ["s9"], Role.TRANSFORM),
            ("join", ["a1", "a2", "a3", "a4"], Role.WALK_COLLECTOR),
        ],
    )
    assert isinstance(plan, WalkPlan)
    assert [i.instance_id for i in plan.instances if i.module_id == "join"] == [
        _iid("join", "w2"),
        _iid("join", "w10"),
    ]
    assert {k: dict(v) for k, v in plan.walk_inputs.items()} == {
        _iid("join", "w2"): {"w11": _iid("a1", "w11"), "w12": _iid("a2", "w12")},
        _iid("join", "w10"): {"w13": _iid("a3", "w13"), "w14": _iid("a4", "w14")},
    }


def test_configurations_nested_branch_paths_in_dfs_index_order(tmp_path: Path) -> None:
    """seed -> b1, b2 and b1 -> c1, c2; paths come out depth-first in index order."""
    from daedalus.core.walks import WalkPlan, configurations
    from daedalus.flow import Role

    plan = _propagate_inline(
        tmp_path / "nested",
        [
            ("seed", [], Role.TRANSFORM),
            ("b1", ["seed"], Role.TRANSFORM),
            ("b2", ["seed"], Role.TRANSFORM),
            ("c1", ["b1"], Role.TRANSFORM),
            ("c2", ["b1"], Role.TRANSFORM),
        ],
    )
    assert isinstance(plan, WalkPlan)
    module_of = {i.instance_id: i.module_id for i in plan.instances}
    paths = [[module_of[iid] for iid in path] for path in configurations(plan)]
    assert paths == [
        ["seed", "b1", "c1"],
        ["seed", "b1", "c2"],
        ["seed", "b2"],
    ]


def test_config_budget_boundary_is_inclusive_and_codes_the_refusal(
    tmp_path: Path,
) -> None:
    """count == budget passes, count > budget refuses; the reason is not pinned."""
    from daedalus.core.walks import WalkDefect, WalkPlan, propagate

    spec, lab_dir = _make_lab(
        tmp_path,
        [
            ("seed", [], "transform"),
            ("left", ["seed"], "transform"),
            ("right", ["seed"], "transform"),
        ],
    )
    # This fork expands to exactly two configuration walks (seed-left, seed-right).
    at_limit = propagate(spec, lab_dir, config_budget=2)  # type: ignore[arg-type]
    assert isinstance(at_limit, WalkPlan)  # count == budget is allowed (<=, not <)

    over_budget = propagate(spec, lab_dir, config_budget=1)  # type: ignore[arg-type]
    assert isinstance(over_budget, WalkDefect)
    assert over_budget.token == "config_walk_budget_exceeded"  # noqa: S105
