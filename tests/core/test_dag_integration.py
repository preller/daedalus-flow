"""Fixture-lab tests for the DiGraph builder, brancher detection and role defects.

Targets are imported inside each test; the in-memory unit tests are in test_dag.py.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.core._dag import _BROKEN_LABS, _FIXTURE_LABS, _write_module


def test_build_graph_is_digraph_with_role_node_attrs() -> None:
    """Nodes are the declared ids with disk roles; id-only mode attaches no role."""
    import networkx as nx

    from daedalus.core.dag import build_dag
    from daedalus.core.recipe import load_recipe, read_module_role

    lab_dir = _FIXTURE_LABS / "linear_smoke"
    spec = load_recipe(lab_dir / "lab.yaml")

    graph = build_dag(spec, lab_dir, with_roles=True)

    assert isinstance(graph, nx.DiGraph)
    assert set(graph.nodes) == {m.id for m in spec.modules}
    for module in spec.modules:
        on_disk = read_module_role(lab_dir / "modules" / module.id)
        assert graph.nodes[module.id]["role"] == on_disk
    assert graph.nodes["emit_ticks"]["role"] == "emitter"
    assert graph.has_edge("emit_ticks", "debug_io")
    # id-only mode (the default) attaches no role attribute.
    id_only = build_dag(spec)
    assert "role" not in id_only.nodes["emit_ticks"]


def test_execution_order_raises_recipe_cycle_error_not_networkxunfeasible() -> None:
    """RecipeCycleError, not a leaked networkx.NetworkXUnfeasible."""
    from daedalus.core.recipe import RecipeCycleError, execution_order, load_recipe

    spec = load_recipe(_BROKEN_LABS / "cyclic.yaml")

    # A leaked NetworkXUnfeasible would fail pytest.raises(RecipeCycleError).
    with pytest.raises(RecipeCycleError):
        execution_order(spec)


def test_cycle_message_names_the_offending_nodes() -> None:
    """The cycle leaf names fit_nested and fit_mcmc; linear_smoke has no defect."""
    from daedalus.core.recipe import first_defect, load_recipe

    cyclic_spec = load_recipe(_BROKEN_LABS / "cyclic.yaml")
    defect = first_defect(cyclic_spec)
    assert defect is not None
    assert "cycle" in defect
    assert "fit_nested" in defect
    assert "fit_mcmc" in defect

    linear_spec = load_recipe(_FIXTURE_LABS / "linear_smoke" / "lab.yaml")
    assert first_defect(linear_spec) is None


def _role_dag(lab_name: str):  # noqa: ANN202 (nx.DiGraph; networkx typed as Any)
    """Build the role-bearing DiGraph for a fixture lab (brancher tests need roles)."""
    from daedalus.core.dag import build_dag
    from daedalus.core.recipe import load_recipe

    lab_dir = _FIXTURE_LABS / lab_name
    return build_dag(load_recipe(lab_dir / "lab.yaml"), lab_dir, with_roles=True)


def test_brancher_predicate_flags_denoise_lightcurve_positive() -> None:
    """A transform with four transform successors is the branch point."""
    from daedalus.core.dag import branchers

    graph = _role_dag("exoplanet_validation")

    assert "denoise_lightcurve" in branchers(graph)


def test_brancher_predicate_does_not_misfire_on_fit_transit_nodes() -> None:
    """Each fit node has out-degree 3 but only walk_collector successors."""
    from daedalus.core.dag import branchers

    graph = _role_dag("exoplanet_validation")

    fit_nodes = {
        "fit_transit_nested",
        "fit_transit_mcmc",
        "fit_transit_gaussian",
        "fit_transit_biased",
    }
    assert branchers(graph) & fit_nodes == set()


def test_brancher_set_on_exoplanet_is_exactly_denoise() -> None:
    """The exact set excludes the emitter, collectors and one-successor transforms."""
    from daedalus.core.dag import branchers

    graph = _role_dag("exoplanet_validation")

    assert branchers(graph) == {"denoise_lightcurve"}


def test_diamond_seed_is_brancher_pinned_with_comment() -> None:
    """seed fans into two transforms; join and the branches are excluded."""
    from daedalus.core.dag import branchers

    graph = _role_dag("diamond_join")

    assert branchers(graph) == {"seed"}


def test_brancher_mixed_successors_counts_only_non_aggregators() -> None:
    """split has two transform successors; split2 has one and is not a brancher."""
    from daedalus.core.dag import branchers

    graph = _role_dag("brancher_mixed")

    found = branchers(graph)
    assert "split" in found
    assert "split2" not in found
    assert found == {"split"}


def test_nested_brancher_both_levels_flagged() -> None:
    """root, l and r each fan into two transforms; the leaves have no successors."""
    from daedalus.core.dag import branchers

    graph = _role_dag("brancher_nested")

    assert branchers(graph) == {"root", "l", "r"}


def test_validate_surface_reads_module_role_from_disk_not_recipe_type() -> None:
    """Every RecipeModule.role is None here, so only the disk role can trip it."""
    from daedalus.core import dag
    from daedalus.core.recipe import load_recipe

    lab_dir = _BROKEN_LABS / "walk_collector_solo"
    spec = load_recipe(lab_dir / "lab.yaml")

    # Nothing in the RecipeSpec carries a role.
    assert all(m.role is None for m in spec.modules)

    leaf = dag.role_defect(spec, lab_dir)
    assert leaf is not None
    assert leaf.startswith("walk_collector_solo")


def _branch_then_collect_lab(lab_dir: Path) -> None:
    """seed -> {left, right} -> d -> join, a walk_collector with the single parent d."""
    for mid, role in (
        ("seed", "transform"),
        ("left", "transform"),
        ("right", "transform"),
        ("d", "transform"),
        ("join", "walk_collector"),
    ):
        _write_module(lab_dir, mid, role)
    (lab_dir / "lab.yaml").write_text(
        "name: 'branch_then_collect'\n"
        "modules:\n"
        "  - id: seed\n"
        "  - id: left\n"
        "    depends: [seed]\n"
        "  - id: right\n"
        "    depends: [seed]\n"
        "  - id: d\n"
        "    depends: [left, right]\n"
        "  - id: join\n"
        "    depends: [d]\n"
    )


def test_solo_pre_pass_fires_only_on_brancherless_labs(tmp_path: Path) -> None:
    """The pre-pass fires only without a brancher; otherwise the token pass decides."""
    from daedalus.core import dag
    from daedalus.core.recipe import load_recipe

    # No brancher, so the static pre-pass fires.
    solo_dir = _BROKEN_LABS / "walk_collector_solo"
    solo_spec = load_recipe(solo_dir / "lab.yaml")
    leaf = dag.role_defect(solo_spec, solo_dir)
    assert leaf is not None
    assert leaf.startswith("walk_collector_solo")

    # With a brancher the pre-pass defers, so role_defect returns None even
    # though join is statically a 1-parent walk_collector.
    branch_then_collect_dir = tmp_path / "branch_then_collect"
    _branch_then_collect_lab(branch_then_collect_dir)
    branch_then_collect_spec = load_recipe(branch_then_collect_dir / "lab.yaml")
    assert dag.role_defect(branch_then_collect_spec, branch_then_collect_dir) is None


def test_flight_collector_as_source_refused_via_build_plan() -> None:
    """build_plan's collector-as-source refusal reaches the validate surface."""
    from daedalus.core.recipe import RecipeParseError, build_plan, load_recipe

    lab_dir = _BROKEN_LABS / "flight_collector_source"
    spec = load_recipe(lab_dir / "lab.yaml")

    with pytest.raises(RecipeParseError, match="a collector cannot be the source"):
        build_plan(spec, lab_dir)
