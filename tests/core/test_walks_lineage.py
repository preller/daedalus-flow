"""Walk lineage, the walk record shape, the arithmetic cross-check and the renderer.

Pure propagate pass, exact-value assertions, stdlib fixtures only.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

from tests.core._walks_helpers import (
    _DEMO_LAB,
    _FIXTURE_LABS,
    _make_lab,
    _propagate_fixture,
    _propagate_inline,
)


def test_walk_lineage_is_ancestors_self_and_own_descendants_only() -> None:
    """Ancestors plus own descendants; a sibling subtree is excluded."""
    from daedalus.core.walks import _RenderCtx, _walk_lineage

    # w1 root; w2 and w5 are sibling branches of w1; w3,w4 descend from w2;
    # w6 descends from w5. w2's lineage must exclude the w5/w6 sibling subtree.
    ctx = _RenderCtx(
        by_walk={},
        children_by_birth={},
        collector_meta={},
        records={},
        parent={"w1": None, "w2": "w1", "w3": "w2", "w4": "w2", "w5": "w1", "w6": "w5"},
        emitter=None,
        flight_root=None,
    )

    # Ancestors (w1) + self + own descendants (w3, w4); excludes sibling w5, w6.
    assert _walk_lineage(ctx, "w2") == {"w1", "w2", "w3", "w4"}
    # A leaf has the ancestor chain only, no descendants.
    assert _walk_lineage(ctx, "w3") == {"w1", "w2", "w3"}
    # The root's lineage is the whole forest.
    assert _walk_lineage(ctx, "w1") == {"w1", "w2", "w3", "w4", "w5", "w6"}

    # The closure must reach grandchildren. The forest is built leaf-first, so in
    # dict order the grandchild cannot join in the same fixpoint pass as its parent.
    # A body that never requests another pass would drop it.
    deep = _RenderCtx(
        by_walk={},
        children_by_birth={},
        collector_meta={},
        records={},
        parent={"leaf": "mid", "mid": "root", "root": None},
        emitter=None,
        flight_root=None,
    )
    assert _walk_lineage(deep, "root") == {"root", "mid", "leaf"}


def test_strict_ancestor_in_walks_the_full_parent_chain() -> None:
    """The nearest in-set ancestor up the whole chain; None when there is none."""
    from types import SimpleNamespace

    from daedalus.core.walks import _Pass, _strict_ancestor_in

    # Chain r <- a <- b <- c, plus a sibling leaf d under r. Built leaf-first.
    # The pass is consulted only through ``.parent``, so a minimal stub will do;
    # the cast satisfies the type checker.
    p = cast(
        "_Pass",
        SimpleNamespace(parent={"c": "b", "b": "a", "a": "r", "d": "r", "r": None}),
    )

    # The nearest in-set ancestor is the immediate parent when it is in the set.
    assert _strict_ancestor_in(p, "c", {"b"}) == "b"
    # A grandparent / great-grandparent in the set is reached by walking up.
    assert _strict_ancestor_in(p, "c", {"a"}) == "a"
    assert _strict_ancestor_in(p, "c", {"r"}) == "r"
    # The nearest wins when several ancestors are in the set.
    assert _strict_ancestor_in(p, "c", {"a", "r"}) == "a"
    # A sibling is not an ancestor; no in-set ancestor yields None.
    assert _strict_ancestor_in(p, "a", {"d"}) is None
    # A root has no strict ancestor at all.
    assert _strict_ancestor_in(p, "r", {"a", "b"}) is None


def test_broadcast_prefixes_collects_every_in_set_ancestor() -> None:
    """Strict ancestors of another in-set token, across levels; siblings excluded."""
    from types import SimpleNamespace

    from daedalus.core.walks import _broadcast_prefixes, _Pass

    # r <- a <- b <- c ; d is a sibling leaf under r. Built leaf-first. Only the
    # ``.parent`` forest is consulted, so the minimal stub is a faithful input.
    p = cast(
        "_Pass",
        SimpleNamespace(parent={"c": "b", "b": "a", "a": "r", "d": "r", "r": None}),
    )

    # r and a are strict ancestors of in-set tokens (a of c through b, r of a).
    # b is not in the set and c, d are leaves, so the prefixes are exactly {r, a}.
    assert _broadcast_prefixes(p, {"r", "a", "c"}) == {"r", "a"}
    # Siblings only; nobody is an ancestor of anybody, so the set is empty.
    assert _broadcast_prefixes(p, {"a", "d"}) == set()
    # A single token has no other token to be a prefix of -> empty.
    assert _broadcast_prefixes(p, {"c"}) == set()


def test_walk_id_counter_order_and_records(tmp_path: Path) -> None:
    """w1, the flight root, then branchers in topological order; a flat counter."""
    import dataclasses

    from daedalus.core.walks import WalkPlan, WalkRecord

    assert [f.name for f in dataclasses.fields(WalkRecord)] == [
        "walk_id",
        "flight_id",
        "parent_walk",
        "born_at",
        "branch_module",
    ]

    demo = _propagate_fixture(_DEMO_LAB)
    assert isinstance(demo, WalkPlan)
    assert demo.walks == (
        WalkRecord("w1", None, None, None, None),
        WalkRecord("w2", "f1", "w1", "emit_targets", None),
        WalkRecord("w3", "f1", "w2", "fetch_data", "fit_mcmc"),
        WalkRecord("w4", "f1", "w2", "fetch_data", "fit_nested"),
    )

    nested = _propagate_inline(
        tmp_path,
        [
            ("src", [], "transform"),
            ("mid", ["src"], "transform"),
            ("side", ["src"], "transform"),
            ("sub_a", ["mid"], "transform"),
            ("sub_b", ["mid"], "transform"),
            ("sub_join", ["sub_a", "sub_b"], "walk_collector"),
            ("top_join", ["sub_join", "side"], "walk_collector"),
        ],
    )
    assert isinstance(nested, WalkPlan)
    assert nested.walks == (
        WalkRecord("w1", None, None, None, None),
        WalkRecord("w2", None, "w1", "src", "mid"),
        WalkRecord("w3", None, "w1", "src", "side"),
        WalkRecord("w4", None, "w2", "mid", "sub_a"),
        WalkRecord("w5", None, "w2", "mid", "sub_b"),
    )
    # top_join closes {w2, w3} where w2's tail is sub_join's instance.
    assert nested.walk_inputs["top_join@w1"] == {
        "w2": "sub_join@w2",
        "w3": "side@w3",
    }


def test_arithmetic_sanity_on_fully_collected_shapes(tmp_path: Path) -> None:
    """Standalone bookkeeping reproduces the walk count on three collected shapes."""
    from daedalus.core.dag import build_dag
    from daedalus.core.recipe import load_recipe
    from daedalus.core.walks import WalkPlan, _arithmetic_walk_count, propagate

    diamond_dir = _FIXTURE_LABS / "diamond_join"
    diamond_spec = load_recipe(diamond_dir / "lab.yaml")
    diamond = propagate(diamond_spec, diamond_dir)
    assert isinstance(diamond, WalkPlan)
    assert len(diamond.walks) == 3
    graph = build_dag(diamond_spec, diamond_dir, with_roles=True)
    assert _arithmetic_walk_count(graph) == 3

    wide4_spec, wide4_dir = _make_lab(
        tmp_path / "wide4",
        [
            ("src", [], "transform"),
            ("b_a", ["src"], "transform"),
            ("b_b", ["src"], "transform"),
            ("b_c", ["src"], "transform"),
            ("b_d", ["src"], "transform"),
            ("join", ["b_a", "b_b", "b_c", "b_d"], "walk_collector"),
        ],
    )
    wide4 = propagate(wide4_spec, wide4_dir)  # type: ignore[arg-type]
    assert isinstance(wide4, WalkPlan)
    assert len(wide4.walks) == 5
    graph = build_dag(wide4_spec, wide4_dir, with_roles=True)  # type: ignore[arg-type]
    assert _arithmetic_walk_count(graph) == 5

    nested_spec, nested_dir = _make_lab(
        tmp_path / "nested",
        [
            ("src", [], "transform"),
            ("mid", ["src"], "transform"),
            ("side", ["src"], "transform"),
            ("sub_a", ["mid"], "transform"),
            ("sub_b", ["mid"], "transform"),
            ("sub_join", ["sub_a", "sub_b"], "walk_collector"),
            ("top_join", ["sub_join", "side"], "walk_collector"),
        ],
    )
    nested = propagate(nested_spec, nested_dir)  # type: ignore[arg-type]
    assert isinstance(nested, WalkPlan)
    assert len(nested.walks) == 5
    graph = build_dag(nested_spec, nested_dir, with_roles=True)  # type: ignore[arg-type]
    assert _arithmetic_walk_count(graph) == 5


def test_walk_strings_match_matrix_literals(tmp_path: Path) -> None:
    """The Full and Walks lines, run to sink, (N) marking the walk-collector."""
    from daedalus.core.walks import WalkPlan

    diamond = _propagate_fixture(_FIXTURE_LABS / "diamond_join")
    assert isinstance(diamond, WalkPlan)
    assert diamond.walk_lines() == (
        "Full:  1-(2,3)-4",
        "Walks: 2",
        "  walk_1: 1-2-(4)",
        "  walk_2: 1-3-(4)",
    )

    branch_then_collect = _propagate_inline(
        tmp_path / "branch_then_collect",
        [
            ("seed", [], "transform"),
            ("left", ["seed"], "transform"),
            ("right", ["seed"], "transform"),
            ("d", ["left", "right"], "transform"),
            ("join", ["d"], "walk_collector"),
        ],
    )
    assert isinstance(branch_then_collect, WalkPlan)
    assert branch_then_collect.walk_lines() == (
        "Full:  1-(2-4,3-4)-5",
        "Walks: 2",
        "  walk_1: 1-2-4-(5)",
        "  walk_2: 1-3-4-(5)",
    )

    demo = _propagate_fixture(_DEMO_LAB)
    assert isinstance(demo, WalkPlan)
    assert demo.walk_lines() == (
        "Full:  1-2-(3,4)-5-6",
        "Walks: 2",
        "  walk_1: 1-2-3-(5)-6",
        "  walk_2: 1-2-4-(5)-6",
    )

    repeat = _propagate_inline(
        tmp_path / "repeat",
        [
            ("seed", [], "transform"),
            ("left", ["seed"], "transform"),
            ("right", ["seed"], "transform"),
            ("d", ["left", "right"], "transform"),
        ],
    )
    assert isinstance(repeat, WalkPlan)
    assert repeat.walk_lines() == (
        "Full:  1-(2-4,3-4)",
        "Walks: 2",
        "  walk_1: 1-2-4",
        "  walk_2: 1-3-4",
    )

    linear = _propagate_fixture(_FIXTURE_LABS / "linear_smoke")
    assert isinstance(linear, WalkPlan)
    assert linear.walk_lines() == (
        "Full:  1-2-3-4-5",
        "Walks: 1",
        "  walk_1: 1-2-3-4-5",
    )


def test_walk_lines_no_flight_wrapper(tmp_path: Path) -> None:
    """No <f1> or f1 = flight syntax; every line is plain ASCII."""
    from daedalus.core.walks import WalkPlan

    for lab in (
        _DEMO_LAB,
        _FIXTURE_LABS / "diamond_join",
        _FIXTURE_LABS / "linear_smoke",
    ):
        plan = _propagate_fixture(lab)
        assert isinstance(plan, WalkPlan)
        block = "\n".join(plan.walk_lines())
        assert "<f1>" not in block
        assert "f1 = " not in block
        assert block.isascii()


def test_walk_lines_merge_marker_on_collected(tmp_path: Path) -> None:
    """A collected walk carries (N) at the collector; an uncollected one has none."""
    from daedalus.core.walks import WalkPlan

    demo = _propagate_fixture(_DEMO_LAB)
    assert isinstance(demo, WalkPlan)
    walk_block = [ln for ln in demo.walk_lines() if ln.lstrip().startswith("walk_")]
    assert all("(5)" in ln for ln in walk_block)

    repeat = _propagate_inline(
        tmp_path / "repeat",
        [
            ("seed", [], "transform"),
            ("left", ["seed"], "transform"),
            ("right", ["seed"], "transform"),
            ("d", ["left", "right"], "transform"),
        ],
    )
    assert isinstance(repeat, WalkPlan)
    repeat_block = [ln for ln in repeat.walk_lines() if ln.lstrip().startswith("walk_")]
    assert all("(" not in ln for ln in repeat_block)


def test_user_walk_dense_rank_per_flight() -> None:
    """On demo the branches map to walk_1, walk_2; root and flight root to None."""
    from daedalus.core.walks import WalkPlan, user_walk

    demo = _propagate_fixture(_DEMO_LAB)
    assert isinstance(demo, WalkPlan)
    by_id = {w.walk_id: w for w in demo.walks}
    mapping = {wid: user_walk(rec, demo.walks) for wid, rec in by_id.items()}
    assert mapping == {
        "w1": None,  # global root (flow scope)
        "w2": None,  # flight root (flight scope)
        "w3": "walk_1",  # fit_mcmc branch
        "w4": "walk_2",  # fit_nested branch
    }

    diamond = _propagate_fixture(_FIXTURE_LABS / "diamond_join")
    assert isinstance(diamond, WalkPlan)
    by_id = {w.walk_id: w for w in diamond.walks}
    mapping = {wid: user_walk(rec, diamond.walks) for wid, rec in by_id.items()}
    assert mapping == {"w1": None, "w2": "walk_1", "w3": "walk_2"}


def test_user_walk_is_presentation_only_walk_id_unchanged() -> None:
    """The internal walk ids stay w1, w2, ... under the presentation numbering."""
    from daedalus.core.walks import WalkPlan

    demo = _propagate_fixture(_DEMO_LAB)
    assert isinstance(demo, WalkPlan)
    assert [w.walk_id for w in demo.walks] == ["w1", "w2", "w3", "w4"]
