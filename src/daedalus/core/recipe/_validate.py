"""Recipe validation, the structural-defect analysis and the deterministic order.

The graph-shaped half of the recipe package over a parsed :class:`RecipeSpec`:
the cycle and dangling-dep detectors, the ordered ``first_defect`` classifier
behind ``validate``, the ``execution_order`` toposort, and the
``linearity_defect`` run-refusal predicate. ``networkx`` and
``daedalus.core.dag`` are imported inside the functions that need them, so the
``dae --help`` path stays free of networkx and the dag import stays deferred.
"""

from __future__ import annotations

from ._parse import _EMITTER_TYPE, RecipeSpec


class RecipeCycleError(Exception):
    """The recipe's depends graph is cyclic, so no execution order exists."""


def _declared_ids(spec: RecipeSpec) -> set[str]:
    return {module.id for module in spec.modules}


def _has_cycle(spec: RecipeSpec) -> bool:
    """True when the depends graph over declared ids is not a DAG (networkx)."""
    import networkx as nx  # noqa: PLC0415 (lazy: off the dae --help path)

    from daedalus.core.dag import _to_digraph  # noqa: PLC0415 (dag imports recipe)

    return not nx.is_directed_acyclic_graph(_to_digraph(spec))


def _cycle_node_ids(spec: RecipeSpec) -> tuple[str, ...]:
    """The node ids on a detected cycle, in edge order; ``()`` when acyclic."""
    import networkx as nx  # noqa: PLC0415 (lazy: off the dae --help path)

    from daedalus.core.dag import _to_digraph  # noqa: PLC0415 (dag imports recipe)

    try:
        edges = nx.find_cycle(_to_digraph(spec))
    except nx.NetworkXNoCycle:
        return ()
    return tuple(edge[0] for edge in edges)


def _dangling_dep(spec: RecipeSpec) -> tuple[str, str] | None:
    """The first ``(module_id, missing_dep)`` whose dep is not a declared id."""
    ids = _declared_ids(spec)
    for module in spec.modules:
        missing = next((d for d in module.depends if d not in ids), None)
        if missing is not None:
            return (module.id, missing)
    return None


def first_defect(spec: RecipeSpec) -> str | None:
    """The first structural defect in a recipe, in a fixed order, or ``None``.

    Returns a leaf token (``two_emitters``, ``dangling_dep``, ``cycle``) suffixed
    with a reason; the caller maps the token to its ``dae.lab.validate.*`` code.
    ``two_emitters`` counts the lab.yaml ``role:`` field, not the run-path role.
    """
    emitters = [m.id for m in spec.modules if m.role == _EMITTER_TYPE]
    if len(emitters) > 1:
        return (
            f"two_emitters: a lab may have only one emitter; found "
            f"{len(emitters)}: {', '.join(emitters)}."
        )
    dangling = _dangling_dep(spec)
    if dangling is not None:
        owner, missing = dangling
        return (
            f"dangling_dep: module '{owner}' depends on '{missing}', which is "
            "not declared."
        )
    if _has_cycle(spec):
        return (
            f"cycle: {', '.join(_cycle_node_ids(spec))} form a cycle "
            "in the recipe graph."
        )
    return None


def execution_order(spec: RecipeSpec) -> tuple[str, ...]:
    """Return the deterministic execution order of the spec's module ids.

    The order is ``networkx.lexicographical_topological_sort(key=str)`` over the
    id-only graph, so ties break by id string, not insertion order; undeclared
    deps are dropped, as ``_to_digraph`` does. Raises RecipeCycleError on a cycle.
    """
    import networkx as nx  # noqa: PLC0415 (lazy: off the dae --help path)

    from daedalus.core.dag import _to_digraph  # noqa: PLC0415 (dag imports recipe)

    try:
        return tuple(nx.lexicographical_topological_sort(_to_digraph(spec), key=str))
    except nx.NetworkXUnfeasible as error:
        raise RecipeCycleError(
            "the recipe graph has a cycle; no order exists."
        ) from error


def linearity_defect(spec: RecipeSpec) -> str | None:
    """Return why the spec is not a single linear chain, or ``None`` if it is.

    Linear means at least one module, at most one depend each, no fan-out, and
    exactly one root; an empty spec is non-linear. Sound only after
    ``first_defect`` passes, which catches a detached cycle this check misses.
    """
    if not spec.modules:
        return "an empty lab has no modules to run."

    fan_in = next((m.id for m in spec.modules if len(m.depends) > 1), None)
    if fan_in is not None:
        return f"module '{fan_in}' depends on more than one module (a join)."

    dependent_count: dict[str, int] = {m.id: 0 for m in spec.modules}
    for module in spec.modules:
        for dep in module.depends:
            if dep in dependent_count:
                dependent_count[dep] += 1
    fan_out = next((mid for mid, count in dependent_count.items() if count > 1), None)
    if fan_out is not None:
        return f"module '{fan_out}' is depended on by more than one module."

    roots = [m.id for m in spec.modules if not m.depends]
    if len(roots) != 1:
        return f"a linear lab needs exactly one root; found {len(roots)}."

    return None
