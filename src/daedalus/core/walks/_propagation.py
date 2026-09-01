"""The forward token-set propagation pass, the walk model.

One forward pass over the static role graph in lexicographic topological
order, with a transfer rule per role. A brancher edge mints a child walk token.
A transform takes its maximal-under-prefix tokens. A walk_collector merges each
complete branch set back onto the parent walk. The flight_collector accepts
only root-scope tokens. The pass is pure and M is fixed at 1; the scheduler
consumes the G* edges, the engine the instances and walk records.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import networkx as nx

from daedalus.core.dag import _AGGREGATOR_ROLES, build_dag, is_brancher
from daedalus.core.walks._arithmetic import _assert_arithmetic
from daedalus.core.walks._config import (
    _config_budget_defect,
    _config_full_line,
    _render_lines,
)
from daedalus.core.walks._shared import (
    _FLIGHT_ID,
    _GLOBAL_ROOT,
    _RESERVED_SEPARATOR,
    DEFAULT_CONFIG_BUDGET,
    DEFAULT_WALK_BUDGET,
    Instance,
    WalkDefect,
    WalkPlan,
    WalkRecord,
    _instance_id,
    _module_of,
    _walk_num,
)
from daedalus.flow import Role

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from daedalus.core.recipe import RecipeSpec

# The flight template needs a single root: an emitter with this many or
# more successors is refused (mirrors dag.py's _MIN_BRANCH_SUCCESSORS style).
_MIN_MULTI_SUCCESSORS = 2


def _reserved_separator_defect(spec: RecipeSpec) -> WalkDefect | None:
    """Static pre-check, before any graph work: '@' is banned in module ids."""
    for module in spec.modules:
        if _RESERVED_SEPARATOR not in module.id:
            continue
        return WalkDefect(
            "reserved_separator_in_id",
            f"module id '{module.id}' contains the reserved separator "
            f"'{_RESERVED_SEPARATOR}'; instance ids '<module>@w<id>' must "
            "parse unambiguously and map injectively to directories, so "
            f"'{_RESERVED_SEPARATOR}' is banned in module ids.",
        )
    return None


def _emitter_node(graph: Any) -> str | None:
    """The lab's emitter module id (on-disk role), or None for static labs."""
    emitters = sorted(
        node for node in graph if graph.nodes[node].get("role") == Role.EMITTER.value
    )
    return emitters[0] if emitters else None


def _emitter_multi_successor_defect(
    graph: Any, emitter: str | None
) -> WalkDefect | None:
    """Static pre-check; the flight template needs a single root."""
    if emitter is None:
        return None
    successors = sorted(graph.successors(emitter))
    if len(successors) < _MIN_MULTI_SUCCESSORS:
        return None
    return WalkDefect(
        "emitter_multi_successor",
        f"emitter '{emitter}' has {len(successors)} successors "
        f"({', '.join(successors)}); the flight template needs a single "
        "root, so an emitter must have exactly one successor.",
    )


def propagate(
    spec: RecipeSpec,
    lab_dir: Path,
    *,
    walk_budget: int = DEFAULT_WALK_BUDGET,
    config_budget: int = DEFAULT_CONFIG_BUDGET,
) -> WalkPlan | WalkDefect:
    """Run the token-set propagation pass over ``spec`` at M=1.

    The caller has already cleared ``first_defect`` and ``role_defect``, so the
    graph is acyclic with validated roles. Returns the WalkPlan or the first
    WalkDefect, in the order separator, multi-successor, token pass, budgets.
    """
    separator = _reserved_separator_defect(spec)
    if separator is not None:
        return separator
    graph = build_dag(spec, lab_dir, with_roles=True)
    emitter = _emitter_node(graph)
    multi = _emitter_multi_successor_defect(graph, emitter)
    if multi is not None:
        return multi
    pass_state = _new_pass(graph, emitter)
    defect = _run(pass_state)
    if defect is not None:
        return defect
    over_budget = _budget_defect(pass_state, walk_budget)
    if over_budget is not None:
        return over_budget
    plan = _build_plan(pass_state)
    over_configs = _config_budget_defect(plan, config_budget)
    if over_configs is not None:
        return over_configs
    return plan


@dataclass
class _Pass:
    """Mutable working state for one propagation pass."""

    graph: Any
    emitter: str | None
    order: list[str]  # lexicographic topological order
    index_of: dict[str, int]
    roles: dict[str, str]
    records: dict[str, WalkRecord]
    parent: dict[str, str | None]  # ancestry forest; the prefix order over tokens
    counter: int
    flight_root: str | None
    tokens_of: dict[str, list[str]]  # module -> instance tokens, sorted
    edge_children: dict[tuple[str, str], dict[str, str]]  # per edge, parent -> child
    gstar: set[tuple[str, str]]  # instance-level edges
    walk_inputs: dict[str, dict[str, str]]
    collector_meta: dict[str, tuple[str | None, str]]  # instance -> (born_at, parent)


def _new_pass(graph: Any, emitter: str | None) -> _Pass:
    """Initialize the pass with w1; the flight root is minted next (M=1)."""
    order = list(nx.lexicographical_topological_sort(graph, key=str))
    index_of = {module_id: i for i, module_id in enumerate(order, start=1)}
    roles = {node: str(graph.nodes[node]["role"]) for node in graph}
    pass_state = _Pass(
        graph=graph,
        emitter=emitter,
        order=order,
        index_of=index_of,
        roles=roles,
        records={_GLOBAL_ROOT: WalkRecord(_GLOBAL_ROOT, None, None, None, None)},
        parent={_GLOBAL_ROOT: None},
        counter=1,
        flight_root=None,
        tokens_of={},
        edge_children={},
        gstar=set(),
        walk_inputs={},
        collector_meta={},
    )
    if emitter is not None:
        pass_state.flight_root = _mint(
            pass_state, _FLIGHT_ID, _GLOBAL_ROOT, emitter, None
        )
    return pass_state


def _mint(
    p: _Pass,
    flight_id: str | None,
    parent_walk: str,
    born_at: str,
    branch_module: str | None,
) -> str:
    """Mint the next walk id off the flat per-flow counter."""
    p.counter += 1
    walk_id = f"w{p.counter}"
    record = WalkRecord(walk_id, flight_id, parent_walk, born_at, branch_module)
    p.records[walk_id] = record
    p.parent[walk_id] = parent_walk
    return walk_id


def _edge_token(p: _Pass, u: str, v: str, token: str) -> str:
    """The out-rule on edge (u, v): emitter boundary, branch edge, or pass-through."""
    if u == p.emitter and p.flight_root is not None:
        return p.flight_root
    children = p.edge_children.get((u, v))
    if children is not None:
        return children[token]
    return token


def _incoming(p: _Pass, v: str) -> dict[str, set[str]]:
    """Union of edge tokens over all in-edges of v, with their parent instances."""
    incoming: dict[str, set[str]] = {}
    for u in sorted(p.graph.predecessors(v)):
        for token in p.tokens_of[u]:
            out_token = _edge_token(p, u, v, token)
            incoming.setdefault(out_token, set()).add(_instance_id(u, token))
    return incoming


def _strict_ancestor_in(p: _Pass, token: str, token_set: set[str]) -> str | None:
    """The nearest strict ancestor of ``token`` present in ``token_set``."""
    current = p.parent.get(token)
    while current is not None:
        if current in token_set:
            return current
        current = p.parent.get(current)
    return None


def _broadcast_prefixes(p: _Pass, token_set: set[str]) -> set[str]:
    """Tokens in the set that are strict ancestors of other tokens in the set."""
    prefixes: set[str] = set()
    for token in token_set:
        ancestor = _strict_ancestor_in(p, token, token_set)
        while ancestor is not None:
            prefixes.add(ancestor)
            ancestor = _strict_ancestor_in(p, ancestor, token_set)
    return prefixes


def _mint_branch_walks(p: _Pass, v: str) -> None:
    """Mint one child walk per (sorted non-collector successor, parent token)."""
    successors = sorted(
        s for s in p.graph.successors(v) if p.roles[s] not in _AGGREGATOR_ROLES
    )
    for successor in successors:
        children = p.edge_children.setdefault((v, successor), {})
        for token in p.tokens_of[v]:
            flight = p.records[token].flight_id
            children[token] = _mint(p, flight, token, v, successor)


def _wire_parent_edges(p: _Pass, v: str, incoming: dict[str, set[str]]) -> None:
    """G* edges for a per-token instance: each token's parents feed v@token."""
    for token, parents in incoming.items():
        target = _instance_id(v, token)
        for parent_instance in sorted(parents):
            p.gstar.add((parent_instance, target))


def _wire_root_edges(p: _Pass, v: str, incoming: dict[str, set[str]]) -> None:
    """G* edges for a single root-scope instance: every parent feeds v@w1."""
    target = _instance_id(v, _GLOBAL_ROOT)
    for parents in incoming.values():
        for parent_instance in sorted(parents):
            p.gstar.add((parent_instance, target))


def _process_transform(p: _Pass, v: str) -> WalkDefect | None:
    """Transform rule, one instance per maximal-under-prefix token."""
    incoming = _incoming(p, v)
    if not incoming:
        incoming = {_GLOBAL_ROOT: set()}
    tokens = sorted(incoming, key=_walk_num)
    token_set = set(tokens)
    for token in tokens:
        ancestor = _strict_ancestor_in(p, token, token_set)
        if ancestor is not None:
            return _broadcast_defect(v, ancestor, token)
    p.tokens_of[v] = tokens
    _wire_parent_edges(p, v, incoming)
    if is_brancher(p.graph, v):
        _mint_branch_walks(p, v)
    return None


def _broadcast_defect(v: str, ancestor: str, token: str) -> WalkDefect:
    """The v1 out-of-model leaf, with no validate code; run maps it to unsupported."""
    return WalkDefect(
        "transform_broadcast_unsupported",
        f"transform '{v}' receives an ancestor broadcast input on walk "
        f"'{ancestor}' alongside the on-walk input on '{token}'; v1 refuses "
        "multi-parent broadcast transforms; add a walk_collector before "
        "this module.",
    )


def _process_emitter(p: _Pass, v: str) -> WalkDefect | None:
    """Emitter rule, one instance on the global root walk (M=1, single root)."""
    incoming = _incoming(p, v)
    p.tokens_of[v] = [_GLOBAL_ROOT]
    _wire_root_edges(p, v, incoming)
    return None


def _process_flight_collector(p: _Pass, v: str) -> WalkDefect | None:
    """Flight-collector rule, root-scope tokens only; the instance is on w1."""
    incoming = _incoming(p, v)
    branch_tokens = sorted(
        (t for t in incoming if p.records[t].branch_module is not None),
        key=_walk_num,
    )
    if branch_tokens:
        return WalkDefect(
            "walks_reach_flight_collector",
            f"branch walks {', '.join(branch_tokens)} reach flight_collector "
            f"'{v}' uncollected; in v1 every branch walk must be collected "
            "(or end at the sink) before the flight merge.",
        )
    p.tokens_of[v] = [_GLOBAL_ROOT]
    _wire_root_edges(p, v, incoming)
    return None


def _process_walk_collector(p: _Pass, v: str) -> WalkDefect | None:
    """Walk-collector rule, group by parent prefix and merge each complete group."""
    # Reading a closed group is not consumption: sibling collectors over the
    # same group each get their own instance on the same parent walk.
    incoming = _incoming(p, v)
    token_set = set(incoming)
    prefixes = _broadcast_prefixes(p, token_set)
    groupable = sorted(
        (t for t in token_set - prefixes if p.records[t].branch_module is not None),
        key=_walk_num,
    )
    if not groupable:
        return WalkDefect(
            "collector_no_walks",
            f"walk_collector '{v}' receives only the parent/root walk; there "
            "are no branch walks to merge (a collector's own fan-out never "
            "mints walks).",
        )
    groups: dict[str, list[str]] = {}
    for token in groupable:
        parent_token = p.records[token].parent_walk or _GLOBAL_ROOT
        groups.setdefault(parent_token, []).append(token)
    tokens: list[str] = []
    for parent_token in sorted(groups, key=_walk_num):
        members = groups[parent_token]
        defect = _incomplete_group_defect(p, v, parent_token, members)
        if defect is not None:
            return defect
        _wire_collector_instance(p, v, parent_token, members, incoming)
        tokens.append(parent_token)
    p.tokens_of[v] = tokens
    _wire_broadcast_ordering(p, v, prefixes, incoming, tokens)
    return None


def _branch_set(p: _Pass, parent_token: str, born_at: str | None) -> set[str]:
    """All branch walks minted at brancher ``born_at`` on ``parent_token``."""
    return {
        walk_id
        for walk_id, record in p.records.items()
        if record.parent_walk == parent_token
        and record.born_at == born_at
        and record.branch_module is not None
    }


def _incomplete_group_defect(
    p: _Pass, v: str, parent_token: str, members: list[str]
) -> WalkDefect | None:
    """Each group must equal one brancher's complete branch set, else defect."""
    born = {p.records[m].born_at for m in members}
    complete = False
    if len(born) == 1:
        expected = _branch_set(p, parent_token, next(iter(born)))
        complete = set(members) == expected
    if complete:
        return None
    return WalkDefect(
        "collector_incomplete_group",
        f"walk_collector '{v}' merges walks {', '.join(members)} on parent "
        f"walk '{parent_token}', which is not one brancher's complete branch "
        "set; a collector must merge exactly the complete sibling group of "
        "one brancher; partial, cross-brancher and cross-level merges are refused.",
    )


def _wire_collector_instance(
    p: _Pass,
    v: str,
    parent_token: str,
    members: list[str],
    incoming: dict[str, set[str]],
) -> None:
    """One collector instance per group, with walk-id-keyed tails plus G* edges."""
    instance = _instance_id(v, parent_token)
    inputs: dict[str, str] = {}
    for member in members:
        parents = sorted(incoming[member])
        tail = max(parents, key=lambda iid: p.index_of[_module_of(iid)])
        inputs[member] = tail
        for parent_instance in parents:
            p.gstar.add((parent_instance, instance))
    p.walk_inputs[instance] = inputs
    p.collector_meta[instance] = (p.records[members[0]].born_at, parent_token)


def _wire_broadcast_ordering(
    p: _Pass,
    v: str,
    prefixes: set[str],
    incoming: dict[str, set[str]],
    tokens: list[str],
) -> None:
    """Ancestor-token parents feed every instance of the collector (ordering)."""
    for prefix in sorted(prefixes, key=_walk_num):
        for parent_instance in sorted(incoming[prefix]):
            for token in tokens:
                p.gstar.add((parent_instance, _instance_id(v, token)))


_HANDLERS: dict[str, Callable[[_Pass, str], WalkDefect | None]] = {
    Role.EMITTER.value: _process_emitter,
    Role.WALK_COLLECTOR.value: _process_walk_collector,
    Role.FLIGHT_COLLECTOR.value: _process_flight_collector,
}


def _run(p: _Pass) -> WalkDefect | None:
    """One forward pass in lexicographic topological order; first defect wins."""
    for module_id in p.order:
        handler = _HANDLERS.get(p.roles[module_id], _process_transform)
        defect = handler(p, module_id)
        if defect is not None:
            return defect
    return None


def _budget_defect(p: _Pass, walk_budget: int) -> WalkDefect | None:
    """The instance-count budget guard, run after the token pass."""
    count = sum(len(tokens) for tokens in p.tokens_of.values())
    if count <= walk_budget:
        return None
    return WalkDefect(
        "walk_budget_exceeded",
        f"the lab expands to {count} step instances per flight, over the "
        f"walk budget of {walk_budget}; an exponential fan-out must be opted "
        "into knowingly, and is refused rather than truncated.",
    )


def _build_plan(p: _Pass) -> WalkPlan:
    """Assemble the frozen WalkPlan; run the wired arithmetic cross-check."""
    instances = tuple(
        Instance(_instance_id(m, t), m, t, p.index_of[m])
        for m in p.order
        for t in p.tokens_of[m]
    )
    edges = tuple(sorted(p.gstar))
    edge_sources = {source for source, _ in edges}
    terminal = tuple(
        sorted(i.instance_id for i in instances if i.instance_id not in edge_sources)
    )
    walks = tuple(p.records[w] for w in sorted(p.records, key=_walk_num))
    lines = _render_lines(p, instances, terminal)
    config_full = _config_full_line(p, instances)
    _assert_arithmetic(p, len(walks), terminal)
    walk_inputs: dict[str, dict[str, str]] = {
        instance: dict(inputs) for instance, inputs in p.walk_inputs.items()
    }
    return WalkPlan(
        walks,
        instances,
        edges,
        walk_inputs,
        terminal,
        dict(p.roles),
        config_full,
        lines,
    )
