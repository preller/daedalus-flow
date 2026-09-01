"""The arithmetic walk-count cross-check (validate-time sanity bookkeeping)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import networkx as nx

from daedalus.core.dag import _AGGREGATOR_ROLES, is_brancher
from daedalus.core.walks._shared import (
    WalkInvariantError,
    _module_of,
    _walk_of,
)
from daedalus.flow import Role

if TYPE_CHECKING:
    from daedalus.core.walks._propagation import _Pass


def _collector_scalar(node: str, incoming_total: int, parent_count: int) -> int:
    """One scalar division step of the bookkeeping; non-integer is a bug smell."""
    if incoming_total % parent_count:
        raise WalkInvariantError(
            f"walk_collector '{node}' divides {incoming_total} by "
            f"{parent_count} to a non-integer; the arithmetic cross-check "
            "diverged (propagation bug)."
        )
    return incoming_total // parent_count


def _branch_successor_count(graph: Any, node: str) -> int:
    """The number of non-collector successors (branch edges) of a node."""
    return sum(
        1
        for successor in graph.successors(node)
        if graph.nodes[successor].get("role") not in _AGGREGATOR_ROLES
    )


def _arithmetic_walk_count(graph: Any) -> int | None:
    """The scalar multiply/divide cross-check, ``None`` outside its scope."""
    multiplicity: dict[str, int] = {}
    minted = 0
    for node in nx.lexicographical_topological_sort(graph, key=str):
        role = graph.nodes[node].get("role")
        if role in (Role.EMITTER.value, Role.FLIGHT_COLLECTOR.value):
            return None
        predecessors = sorted(graph.predecessors(node))
        if not predecessors:
            multiplicity[node] = 1
        elif role == Role.WALK_COLLECTOR.value:
            total = sum(multiplicity[p] for p in predecessors)
            multiplicity[node] = _collector_scalar(node, total, len(predecessors))
        elif len(predecessors) > 1:
            return None
        else:
            multiplicity[node] = multiplicity[predecessors[0]]
        if is_brancher(graph, node):
            minted += multiplicity[node] * _branch_successor_count(graph, node)
    return 1 + minted


def _assert_arithmetic(p: _Pass, walk_count: int, terminal: tuple[str, ...]) -> None:
    """The validate-time sanity cross-check on fully collected shapes."""
    if not _arithmetic_applicable(p, terminal):
        return
    expected = _arithmetic_walk_count(p.graph)
    if expected is None or expected == walk_count:
        return
    raise WalkInvariantError(
        f"the arithmetic cross-check diverged, the bookkeeping counts {expected} "
        f"walks and the propagation pass produced {walk_count} (propagation bug)."
    )


def _arithmetic_applicable(p: _Pass, terminal: tuple[str, ...]) -> bool:
    """Scalar scope, flightless, repeat-free, fully collected, in-degrees matched."""
    if p.emitter is not None:
        return False
    if any(len(tokens) != 1 for tokens in p.tokens_of.values()):
        return False
    terminal_walks = {_walk_of(instance_id) for instance_id in terminal}
    if any(p.records[w].branch_module is not None for w in terminal_walks):
        return False
    return all(
        p.graph.in_degree(_module_of(instance_id)) == len(inputs)
        for instance_id, inputs in p.walk_inputs.items()
    )
