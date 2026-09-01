"""Build the static NetworkX DiGraph for a parsed lab recipe.

Nodes are the declared module ids; edges run dep -> dependent. ``build_dag``
adds every node first, then refuses a dep on an undeclared id before any
``add_edge`` could create the node. With ``with_roles=True`` it also validates
and attaches each module's on-disk role. ``_to_digraph`` is the lenient
ordering builder and drops unknown deps instead. ``import networkx`` stays off
the bare ``dae --help`` path.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import networkx as nx

from daedalus.core.recipe import (
    _EMITTER_TYPE,
    _VALID_ROLES,
    RecipeParseError,
    RecipeSpec,
    _dangling_dep,
    read_module_role,
)
from daedalus.flow import Role

if TYPE_CHECKING:
    from pathlib import Path

# Successor roles that do not count toward branching: an edge into an
# aggregator is convergence-prep, not a new Walk.
_AGGREGATOR_ROLES = frozenset({Role.WALK_COLLECTOR.value, Role.FLIGHT_COLLECTOR.value})

# A transform with at least this many non-aggregator successors is a brancher;
# a single onward successor is a plain linear hand-off.
_MIN_BRANCH_SUCCESSORS = 2


def _to_digraph(spec: RecipeSpec) -> nx.DiGraph:
    """Id-only graph for ordering; undeclared deps are dropped, not refused."""
    graph = nx.DiGraph()
    graph.add_nodes_from(module.id for module in spec.modules)
    ids = {module.id for module in spec.modules}
    graph.add_edges_from(
        (dep, module.id)
        for module in spec.modules
        for dep in module.depends
        if dep in ids
    )
    return graph


def _validate_no_dangling(spec: RecipeSpec) -> None:
    """Raise RecipeParseError on the first dep that is not a declared id."""
    dangling = _dangling_dep(spec)
    if dangling is not None:
        owner, missing = dangling
        raise RecipeParseError(
            f"module '{owner}' depends on '{missing}', which is not declared."
        )


def _read_validated_role(module_id: str, module_dir: Path) -> str:
    """Read one module's on-disk role and validate it against the closed role set."""
    if not module_dir.is_dir():
        raise RecipeParseError(
            f"module '{module_id}' has no directory at {module_dir}."
        )
    role = read_module_role(module_dir)
    if role is None:
        raise RecipeParseError(
            f"module '{module_id}' has no role in its dae-module.yaml."
        )
    if role not in _VALID_ROLES:
        raise RecipeParseError(
            f"module '{module_id}' has an unknown role {role!r}; "
            f"valid roles are {', '.join(sorted(_VALID_ROLES))}."
        )
    return role


def build_dag(
    spec: RecipeSpec,
    lab_dir: Path | None = None,
    *,
    with_roles: bool = False,
) -> nx.DiGraph:
    """Build the validated static DiGraph for ``spec``, nodes first, then edges.

    A dangling dep raises RecipeParseError before any ``add_edge``. With
    ``with_roles=True`` (needs ``lab_dir``) each module's on-disk role is
    validated and attached as the ``role`` node attribute, or raises too.
    """
    graph = nx.DiGraph()
    graph.add_nodes_from(module.id for module in spec.modules)
    _validate_no_dangling(spec)
    if with_roles:
        if lab_dir is None:
            raise RecipeParseError(
                "build_dag(with_roles=True) requires a lab_dir to read module "
                "roles from."
            )
        for module in spec.modules:
            module_dir = lab_dir / "modules" / module.id
            graph.nodes[module.id]["role"] = _read_validated_role(module.id, module_dir)
    graph.add_edges_from(
        (dep, module.id) for module in spec.modules for dep in module.depends
    )
    return graph


def is_brancher(graph: nx.DiGraph, node: str) -> bool:
    """True when ``node`` is a Walk brancher (auto-detected, never declared).

    A brancher is a transform with at least two non-aggregator successors; an
    edge into a walk or flight collector is convergence, not branching. On an
    id-only graph, where no node carries ``role``, nothing is flagged.
    """
    if graph.nodes[node].get("role") != Role.TRANSFORM.value:
        return False
    non_aggregator_successors = sum(
        1
        for successor in graph.successors(node)
        if graph.nodes[successor].get("role") not in _AGGREGATOR_ROLES
    )
    return non_aggregator_successors >= _MIN_BRANCH_SUCCESSORS


def branchers(graph: nx.DiGraph) -> set[str]:
    """The set of brancher node ids in a role-bearing graph (see is_brancher)."""
    return {node for node in graph if is_brancher(graph, node)}


# A walk-collector converges two or more parallel Walks, so a walk_collector
# with fewer than this many parents converges nothing.
_MIN_WALK_COLLECTOR_PARENTS = 2


def _emitter_not_source_defect(spec: RecipeSpec) -> str | None:
    """Leaf for a lab.yaml emitter that declares depends (keyed on the lab role)."""
    for module in spec.modules:
        if module.role == _EMITTER_TYPE and module.depends:
            depends = ", ".join(module.depends)
            return (
                f"emitter_not_source: module '{module.id}' is marked an emitter "
                f"but depends on {depends}; an emitter is the lab's source and "
                "takes no upstream dependency."
            )
    return None


def _walk_collector_solo_defect(graph: nx.DiGraph) -> str | None:
    """Leaf for a brancherless lab whose walk_collector has fewer than two parents."""
    if branchers(graph):
        return None
    for node in graph:
        if graph.nodes[node].get("role") != Role.WALK_COLLECTOR.value:
            continue
        parents = graph.in_degree(node)
        if parents < _MIN_WALK_COLLECTOR_PARENTS:
            return (
                f"walk_collector_solo: module '{node}' is a walk_collector with "
                f"{parents} parent(s); a walk-collector converges two or more "
                "parallel Walks, so it needs at least two parents."
            )
    return None


def role_defect(spec: RecipeSpec, lab_dir: Path) -> str | None:
    """The first role or structure defect in a recipe, or ``None`` if sound.

    Runs after ``first_defect`` has cleared, so the graph is acyclic. Returns a
    leaf token (``emitter_not_source`` or ``walk_collector_solo``) suffixed with
    a reason, first defect only. Building the role graph may raise RecipeParseError.
    """
    emitter = _emitter_not_source_defect(spec)
    if emitter is not None:
        return emitter
    graph = build_dag(spec, lab_dir, with_roles=True)
    return _walk_collector_solo_defect(graph)
