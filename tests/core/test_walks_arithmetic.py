"""The arithmetic cross-check helpers for scalar walk counts.

Tested on hand-built role graphs, so expected counts derive from the shape.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.core._walks_helpers import _propagate_inline


def _role_graph(roles: dict[str, str], edges: list[tuple[str, str]]) -> Any:  # noqa: ANN401  (networkx DiGraph, imported in body per file convention)
    """Build a role-bearing DiGraph (as ``build_dag(with_roles=True)`` yields)."""
    import networkx as nx

    graph = nx.DiGraph()
    for node, role in roles.items():
        graph.add_node(node, role=role)
    graph.add_edges_from(edges)
    return graph


def test_branch_successor_count_excludes_aggregator_edges() -> None:
    """An edge into a collector is convergence, not a branch."""
    from daedalus.core.walks import _branch_successor_count
    from daedalus.flow import Role

    onward = ["t1", "t2"]
    roles = {"seed": Role.TRANSFORM.value, "c": Role.WALK_COLLECTOR.value}
    roles.update({t: Role.TRANSFORM.value for t in onward})
    edges = [("seed", t) for t in onward] + [("seed", "c")]
    graph = _role_graph(roles, edges)

    # The collector edge is excluded; only the two onward transforms count.
    assert _branch_successor_count(graph, "seed") == len(onward)


def test_collector_scalar_divides_and_rejects_non_integer() -> None:
    """Exact integer quotient; a non-integer quotient raises WalkInvariantError."""
    from daedalus.core.walks import WalkInvariantError, _collector_scalar

    quotient = _collector_scalar("c", 6, 3)
    assert quotient == 2
    # A float would still satisfy == 2, so the type is checked as well.
    assert isinstance(quotient, int)
    with pytest.raises(WalkInvariantError) as exc:
        _collector_scalar("c", 5, 2)
    # The message names the offending operands.
    assert "5" in str(exc.value)
    assert "2" in str(exc.value)


def test_arithmetic_walk_count_is_root_plus_one_per_branch() -> None:
    """A width-N brancher and the root walk count 1 + N."""
    from daedalus.core.walks import _arithmetic_walk_count
    from daedalus.flow import Role

    branches = ["a", "b", "c"]
    roles = {"seed": Role.TRANSFORM.value, "j": Role.WALK_COLLECTOR.value}
    roles.update({b: Role.TRANSFORM.value for b in branches})
    edges = [("seed", b) for b in branches] + [(b, "j") for b in branches]

    assert _arithmetic_walk_count(_role_graph(roles, edges)) == 1 + len(branches)


def test_arithmetic_walk_count_propagates_collector_multiplicity() -> None:
    """The collector's divided multiplicity feeds the downstream brancher w."""
    from daedalus.core.walks import _arithmetic_walk_count
    from daedalus.flow import Role

    roles = {
        "seed": Role.TRANSFORM.value,
        "a": Role.TRANSFORM.value,
        "b": Role.TRANSFORM.value,
        "c": Role.WALK_COLLECTOR.value,
        "w": Role.TRANSFORM.value,
        "x": Role.TRANSFORM.value,
        "y": Role.TRANSFORM.value,
    }
    edges = [
        ("seed", "a"),
        ("seed", "b"),
        ("a", "c"),
        ("b", "c"),
        ("c", "w"),
        ("w", "x"),
        ("w", "y"),
    ]
    # c = (mult[a] + mult[b]) / 2 = 1, so w inherits multiplicity 1 and mints 2;
    # seed also mints 2. Count = 1 root + 2 (seed) + 2 (w). A wrong sum or
    # division would change c's multiplicity and so change this total.
    assert _arithmetic_walk_count(_role_graph(roles, edges)) == 1 + 2 + 2


def test_arithmetic_walk_count_abstains_outside_scalar_scope() -> None:
    """Returns None for an emitter, a flight_collector or a repeated transform."""
    from daedalus.core.walks import _arithmetic_walk_count
    from daedalus.flow import Role

    flight = _role_graph(
        {"e": Role.EMITTER.value, "t": Role.TRANSFORM.value}, [("e", "t")]
    )
    assert _arithmetic_walk_count(flight) is None

    # A flight_collector is equally out of scalar scope, the other half of the
    # early-return guard.
    fc_shape = _role_graph(
        {"a": Role.TRANSFORM.value, "fc": Role.FLIGHT_COLLECTOR.value},
        [("a", "fc")],
    )
    assert _arithmetic_walk_count(fc_shape) is None

    repeat = _role_graph(
        {m: Role.TRANSFORM.value for m in ("seed", "a", "b", "t")},
        [("seed", "a"), ("seed", "b"), ("a", "t"), ("b", "t")],
    )
    assert _arithmetic_walk_count(repeat) is None


def test_config_count_agrees_with_enumeration(tmp_path: Path) -> None:
    """The enumerator is pinned separately by the depth-first test."""
    from daedalus.core.walks import WalkPlan, _config_count, configurations

    # A collected diamond (a node reachable by two paths, the memoized re-convergence)
    # and nested branchers (multi-level fan-out).
    shapes: list[list[tuple[str, list[str], str]]] = [
        [
            ("src", [], "transform"),
            ("b_a", ["src"], "transform"),
            ("b_b", ["src"], "transform"),
            ("join", ["b_a", "b_b"], "walk_collector"),
            ("tail", ["join"], "transform"),
        ],
        [
            ("seed", [], "transform"),
            ("b1", ["seed"], "transform"),
            ("b2", ["seed"], "transform"),
            ("c1", ["b1"], "transform"),
            ("c2", ["b1"], "transform"),
        ],
    ]
    for modules in shapes:
        plan = _propagate_inline(tmp_path / modules[0][0], modules)
        assert isinstance(plan, WalkPlan)
        # The memoized count must equal the enumerated count.
        assert _config_count(plan) == len(configurations(plan))
        # Each shape forks, so strictly more than one configuration.
        assert _config_count(plan) > 1
