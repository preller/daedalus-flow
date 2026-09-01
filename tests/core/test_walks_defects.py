"""One test per defect arm, asserting the exact leaf token.

Pure propagate pass over inline labs, stdlib fixtures only.
"""

from __future__ import annotations

from pathlib import Path

from tests.core._walks_helpers import _propagate_inline


def test_partial_group_is_collector_incomplete_group(tmp_path: Path) -> None:
    """A collector over 2 of 3 branches refuses with the exact token."""
    from daedalus.core.walks import WalkDefect

    result = _propagate_inline(
        tmp_path,
        [
            ("src", [], "transform"),
            ("b_a", ["src"], "transform"),
            ("b_b", ["src"], "transform"),
            ("b_c", ["src"], "transform"),
            ("join", ["b_a", "b_b"], "walk_collector"),
        ],
    )
    assert isinstance(result, WalkDefect)
    assert result.token == "collector_incomplete_group"  # noqa: S105
    # Names the offending collector; the word "join" appears only through the
    # collector id, not in the message prose.
    assert "join" in result.reason


def test_cross_brancher_merge_is_collector_incomplete_group(tmp_path: Path) -> None:
    from daedalus.core.walks import WalkDefect

    result = _propagate_inline(
        tmp_path,
        [
            ("src", [], "transform"),
            ("a", ["src"], "transform"),
            ("b", ["src"], "transform"),
            ("a1", ["a"], "transform"),
            ("a2", ["a"], "transform"),
            ("b1", ["b"], "transform"),
            ("b2", ["b"], "transform"),
            ("join", ["a1", "b1"], "walk_collector"),
        ],
    )
    assert isinstance(result, WalkDefect)
    assert result.token == "collector_incomplete_group"  # noqa: S105


def test_collector_fanout_reconverging_is_collector_no_walks(tmp_path: Path) -> None:
    """Collector out-edges mint no walks, so c2 has nothing to merge."""
    from daedalus.core.walks import WalkDefect

    result = _propagate_inline(
        tmp_path,
        [
            ("src", [], "transform"),
            ("x", ["src"], "transform"),
            ("y", ["src"], "transform"),
            ("c1", ["x", "y"], "walk_collector"),
            ("t_a", ["c1"], "transform"),
            ("t_b", ["c1"], "transform"),
            ("c2", ["t_a", "t_b"], "walk_collector"),
        ],
    )
    assert isinstance(result, WalkDefect)
    assert result.token == "collector_no_walks"  # noqa: S105


def test_branch_walks_into_flight_collector_refused(tmp_path: Path) -> None:
    """Uncollected branch walks reaching the flight_collector refuse."""
    from daedalus.core.walks import WalkDefect

    result = _propagate_inline(
        tmp_path,
        [
            ("emit", [], "emitter"),
            ("prep", ["emit"], "transform"),
            ("b_a", ["prep"], "transform"),
            ("b_b", ["prep"], "transform"),
            ("fcollect", ["b_a", "b_b"], "flight_collector"),
        ],
    )
    assert isinstance(result, WalkDefect)
    assert result.token == "walks_reach_flight_collector"  # noqa: S105


def test_emitter_two_successors_refused(tmp_path: Path) -> None:
    """An emitter with two successors refuses (single flight root)."""
    from daedalus.core.walks import WalkDefect

    result = _propagate_inline(
        tmp_path,
        [
            ("emit", [], "emitter"),
            ("a", ["emit"], "transform"),
            ("b", ["emit"], "transform"),
        ],
    )
    assert isinstance(result, WalkDefect)
    assert result.token == "emitter_multi_successor"  # noqa: S105
    # Names the emitter (quoted, so the interpolated id, not the word "emitter")
    # and its successors in sorted order.
    assert "'emit'" in result.reason
    assert "2 successors" in result.reason
    assert "a, b" in result.reason


def test_eleven_nested_branchers_exceed_walk_budget(tmp_path: Path) -> None:
    """The reason names the instance count and the budget."""
    from daedalus.core.walks import WalkDefect

    modules: list[tuple[str, list[str], str]] = [
        ("b00", [], "transform"),
        ("l01", ["b00"], "transform"),
        ("r01", ["b00"], "transform"),
    ]
    for level in range(1, 11):
        d_id = f"d{level:02d}"
        modules.append((d_id, [f"l{level:02d}", f"r{level:02d}"], "transform"))
        modules.append((f"l{level + 1:02d}", [d_id], "transform"))
        modules.append((f"r{level + 1:02d}", [d_id], "transform"))

    result = _propagate_inline(tmp_path, modules)
    assert isinstance(result, WalkDefect)
    assert result.token == "walk_budget_exceeded"  # noqa: S105
    # 1 + sum(l_k + r_k, k=1..11) + sum(d_k, k=1..10) = 1 + 4094 + 2046.
    assert "6141" in result.reason
    assert "1024" in result.reason


def test_module_id_with_at_sign_refused(tmp_path: Path) -> None:
    """A module id containing '@' is refused statically, pre-propagation."""
    from daedalus.core.walks import _RESERVED_SEPARATOR, WalkDefect

    result = _propagate_inline(
        tmp_path,
        [
            ("a", [], "transform"),
            ("fit@home", ["a"], "transform"),
            ("c", ["fit@home"], "transform"),
        ],
    )
    assert isinstance(result, WalkDefect)
    assert result.token == "reserved_separator_in_id"  # noqa: S105
    # Names the module id and the separator, each quoted; 'fit@home' does not
    # contain the quoted '@', so both interpolations are pinned.
    assert "'fit@home'" in result.reason
    assert f"'{_RESERVED_SEPARATOR}'" in result.reason


def test_broadcast_parent_yields_transform_broadcast_unsupported(
    tmp_path: Path,
) -> None:
    """An ancestor token beside the on-walk token yields the v1 out-of-model leaf."""
    from daedalus.core.walks import WalkDefect

    result = _propagate_inline(
        tmp_path,
        [
            ("seed", [], "transform"),
            ("p", ["seed"], "transform"),
            ("q", ["seed"], "transform"),
            ("j1", ["p", "q"], "walk_collector"),
            ("mid", ["j1"], "transform"),
            ("m", ["mid"], "transform"),
            ("n", ["mid"], "transform"),
            ("tt", ["j1", "m"], "transform"),
        ],
    )
    assert isinstance(result, WalkDefect)
    assert result.token == "transform_broadcast_unsupported"  # noqa: S105
    # Names the offending transform, quoted.
    assert "'tt'" in result.reason
