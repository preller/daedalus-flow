"""Unit tests for the DiGraph builder, execution order and the role-defect checks.

Targets are imported inside each test; disk-role tests are in test_dag_integration.py.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.core._dag import _write_module


def test_build_graph_validates_dangling_before_add_edge_no_roleless_node_leaks(
    tmp_path: Path,
) -> None:
    """networkx add_edge would create the endpoint; the dangling check runs first."""
    from daedalus.core.dag import _to_digraph, build_dag
    from daedalus.core.recipe import RecipeParseError, load_recipe_text

    spec = load_recipe_text("modules:\n  - id: a\n    depends: [ghost]\n")
    module_dir = tmp_path / "modules" / "a"
    module_dir.mkdir(parents=True)
    (module_dir / "dae-module.yaml").write_text("role: transform\n")

    with pytest.raises(RecipeParseError, match="ghost"):
        build_dag(spec)
    with pytest.raises(RecipeParseError, match="ghost"):
        build_dag(spec, tmp_path, with_roles=True)

    lenient = _to_digraph(spec)
    assert "ghost" not in lenient.nodes
    assert set(lenient.nodes) == {"a"}
    assert lenient.number_of_edges() == 0


def test_execution_order_lexicographical_toposort_byte_stable_across_runs() -> None:
    """Five calls on the '10', '2', '1' tie vector give the same order."""
    from daedalus.core.recipe import execution_order, load_recipe_text

    spec = load_recipe_text("modules:\n  - id: '10'\n  - id: '2'\n  - id: '1'\n")

    orders = [execution_order(spec) for _ in range(5)]

    assert all(order == ("1", "10", "2") for order in orders)


def test_execution_order_on_dangling_spec_returns_only_declared_ids() -> None:
    """The ordering builder drops an undeclared dep; only strict build_dag refuses."""
    from daedalus.core.recipe import execution_order, load_recipe_text

    spec = load_recipe_text(
        "modules:\n  - id: a\n    depends: [ghost]\n  - id: b\n    depends: [a]\n"
    )

    order = execution_order(spec)

    assert order == ("a", "b")
    assert "ghost" not in order


# role_defect runs after first_defect (cycle, dangling, two emitters) clears:
# emitter_not_source first, keyed on the lab.yaml role, then walk_collector_solo,
# keyed on the disk role and limited to brancherless labs. First defect only.


def test_brancher_no_collector_is_retired(tmp_path: Path) -> None:
    """A diamond into a transform sink passes role_defect and the token pass."""
    from daedalus.core import dag, walks
    from daedalus.core.outcomes import Outcome
    from daedalus.core.recipe import load_recipe

    # A diamond into a transform sink, refused before the per-group relaxation.
    uncollected = tmp_path / "uncollected"
    for mid, role in (
        ("seed", "transform"),
        ("left", "transform"),
        ("right", "transform"),
        ("sink", "transform"),
    ):
        _write_module(uncollected, mid, role)
    (uncollected / "lab.yaml").write_text(
        "name: 'uncollected'\n"
        "modules:\n"
        "  - id: seed\n"
        "  - id: left\n"
        "    depends: [seed]\n"
        "  - id: right\n"
        "    depends: [seed]\n"
        "  - id: sink\n"
        "    depends: [left, right]\n"
    )
    spec = load_recipe(uncollected / "lab.yaml")
    assert dag.role_defect(spec, uncollected) is None
    assert isinstance(walks.propagate(spec, uncollected), walks.WalkPlan)

    # The retired Outcome member is gone entirely.
    assert not hasattr(Outcome, "DAE_LAB_VALIDATE_BRANCHER_NO_COLLECTOR")


def test_first_defect_order_two_emitters_then_dangling_then_cycle_unchanged(
    tmp_path: Path,
) -> None:
    """The cycle leaf wins; role checks run only after first_defect returns None."""
    from daedalus.core.recipe import first_defect, load_recipe

    # Build a cyclic lab whose solo_agg is also a 1-parent walk_collector.
    lab_dir = tmp_path / "cyclic_solo"
    (lab_dir / "modules" / "a").mkdir(parents=True)
    (lab_dir / "modules" / "solo_agg").mkdir(parents=True)
    (lab_dir / "modules" / "a" / "dae-module.yaml").write_text("role: transform\n")
    (lab_dir / "modules" / "solo_agg" / "dae-module.yaml").write_text(
        "role: walk_collector\n"
    )
    (lab_dir / "lab.yaml").write_text(
        "name: 'cyclic_solo'\n"
        "modules:\n"
        "  - id: a\n"
        "    depends: [solo_agg]\n"
        "  - id: solo_agg\n"
        "    depends: [a]\n"
    )
    spec = load_recipe(lab_dir / "lab.yaml")

    # first_defect reports the cycle; the validate surface consults role_defect
    # only when first_defect returns None.
    defect = first_defect(spec)
    assert defect is not None
    assert defect.partition(":")[0] == "cycle"


def test_validate_is_first_defect_only(tmp_path: Path) -> None:
    """A lab with both role defects reports only emitter_not_source."""
    from daedalus.core import dag
    from daedalus.core.recipe import load_recipe

    lab_dir = tmp_path / "two_defects"
    for mid, role in (
        ("late_emit", "emitter"),
        ("solo_agg", "walk_collector"),
    ):
        (lab_dir / "modules" / mid).mkdir(parents=True)
        (lab_dir / "modules" / mid / "dae-module.yaml").write_text(f"role: {role}\n")
    # late_emit is role: emitter yet depends on solo_agg (emitter_not_source);
    # solo_agg is a 1-parent walk_collector with no brancher (walk_collector_solo).
    # Both defects are present at once.
    (lab_dir / "lab.yaml").write_text(
        "name: 'two_defects'\n"
        "modules:\n"
        "  - id: solo_agg\n"
        "    depends: [late_emit]\n"
        "  - id: late_emit\n"
        "    role: emitter\n"
        "    depends: [solo_agg]\n"
    )
    spec = load_recipe(lab_dir / "lab.yaml")

    leaf = dag.role_defect(spec, lab_dir)
    assert leaf is not None
    # emitter_not_source runs before walk_collector_solo.
    assert leaf.partition(":")[0] == "emitter_not_source"
    assert "walk_collector_solo" not in leaf


def test_missing_module_dir_raises_recipe_parse_error(tmp_path: Path) -> None:
    """RecipeParseError, not a FileNotFoundError traceback and not a skip."""
    from daedalus.core import dag
    from daedalus.core.recipe import RecipeParseError, load_recipe

    lab_dir = tmp_path / "missing_dir"
    (lab_dir / "modules" / "src").mkdir(parents=True)
    (lab_dir / "modules" / "src" / "dae-module.yaml").write_text("role: transform\n")
    # solo_agg is declared (and depends on src) but its module dir is absent.
    (lab_dir / "lab.yaml").write_text(
        "name: 'missing_dir'\n"
        "modules:\n"
        "  - id: src\n"
        "  - id: solo_agg\n"
        "    depends: [src]\n"
    )
    spec = load_recipe(lab_dir / "lab.yaml")

    with pytest.raises(RecipeParseError):
        dag.role_defect(spec, lab_dir)


def test_read_validated_role_returns_role_and_reports_each_failure(
    tmp_path: Path,
) -> None:
    """Asserts return versus raise and the data-derived parts, not the wording."""
    from daedalus.core.dag import _read_validated_role
    from daedalus.core.recipe import RecipeParseError
    from daedalus.flow import Role

    good = tmp_path / "modules" / "good"
    good.mkdir(parents=True)
    (good / "dae-module.yaml").write_text(f"role: {Role.TRANSFORM}\n")
    assert _read_validated_role("good", good) == Role.TRANSFORM

    with pytest.raises(RecipeParseError, match="ghost"):
        _read_validated_role("ghost", tmp_path / "modules" / "ghost")

    norole = tmp_path / "modules" / "norole"
    norole.mkdir(parents=True)
    (norole / "dae-module.yaml").write_text("name: norole\n")
    with pytest.raises(RecipeParseError, match="norole"):
        _read_validated_role("norole", norole)

    bad = tmp_path / "modules" / "bad"
    bad.mkdir(parents=True)
    (bad / "dae-module.yaml").write_text("role: wizard\n")
    with pytest.raises(RecipeParseError, match="wizard"):
        _read_validated_role("bad", bad)


def test_build_dag_with_roles_without_lab_dir_is_refused() -> None:
    """build_dag(with_roles=True) needs a lab_dir: assert the refusal, not wording."""
    from daedalus.core.dag import build_dag
    from daedalus.core.recipe import RecipeParseError, load_recipe_text

    spec = load_recipe_text("name: 'x'\nmodules:\n  - id: a\n")
    with pytest.raises(RecipeParseError):
        build_dag(spec, None, with_roles=True)


def test_build_dag_builds_exact_nodes_edges_and_disk_roles(tmp_path: Path) -> None:
    """Node set, edge set, no roles in id-only mode, disk roles with with_roles."""
    from daedalus.core.dag import build_dag
    from daedalus.core.recipe import load_recipe
    from daedalus.flow import Role

    _write_module(tmp_path, "src", Role.TRANSFORM)
    _write_module(tmp_path, "agg", Role.WALK_COLLECTOR)
    (tmp_path / "lab.yaml").write_text(
        "name: 'roles_lab'\nmodules:\n  - id: src\n  - id: agg\n    depends: [src]\n"
    )
    spec = load_recipe(tmp_path / "lab.yaml")

    id_only = build_dag(spec)
    assert set(id_only.nodes) == {"src", "agg"}
    assert set(id_only.edges) == {("src", "agg")}
    assert all("role" not in id_only.nodes[n] for n in id_only)

    with_roles = build_dag(spec, tmp_path, with_roles=True)
    assert set(with_roles.nodes) == {"src", "agg"}
    assert set(with_roles.edges) == {("src", "agg")}
    assert with_roles.nodes["src"]["role"] == Role.TRANSFORM
    assert with_roles.nodes["agg"]["role"] == Role.WALK_COLLECTOR


def test_emitter_not_source_defect_names_module_and_clears_negatives() -> None:
    """Asserts the defect token and the data-derived id and dep, not the sentence."""
    from daedalus.core.dag import _emitter_not_source_defect
    from daedalus.core.recipe import load_recipe_text
    from daedalus.flow import Role

    bad = load_recipe_text(
        "name: 'x'\nmodules:\n"
        "  - id: src\n"
        f"  - id: em\n    role: {Role.EMITTER}\n    depends: [src]\n"
    )
    leaf = _emitter_not_source_defect(bad)
    assert leaf is not None
    assert leaf.startswith("emitter_not_source")
    assert "'em'" in leaf  # the offending module id (data-derived)
    assert "src" in leaf  # the dependency it must not have (data-derived)

    lone = load_recipe_text(
        f"name: 'x'\nmodules:\n  - id: em\n    role: {Role.EMITTER}\n"
    )
    assert _emitter_not_source_defect(lone) is None

    plain = load_recipe_text(
        "name: 'x'\nmodules:\n  - id: src\n  - id: t\n    depends: [src]\n"
    )
    assert _emitter_not_source_defect(plain) is None


def test_walk_collector_solo_defect_boundary_and_message() -> None:
    """Parent count below 2 fires; two parents or a brancher present does not."""
    import networkx as nx

    from daedalus.core.dag import _walk_collector_solo_defect
    from daedalus.flow import Role

    def _graph(edges, roles):  # noqa: ANN202 (nx.DiGraph; networkx typed as Any)
        graph = nx.DiGraph()
        for node, role in roles.items():
            graph.add_node(node, role=role)
        graph.add_edges_from(edges)
        return graph

    solo = _graph([("a", "c")], {"a": Role.TRANSFORM, "c": Role.WALK_COLLECTOR})
    leaf = _walk_collector_solo_defect(solo)
    assert leaf is not None
    assert leaf.startswith("walk_collector_solo")
    assert "'c'" in leaf  # names the offending collector (data-derived)

    pair = _graph(
        [("a", "c"), ("b", "c")],
        {"a": Role.TRANSFORM, "b": Role.TRANSFORM, "c": Role.WALK_COLLECTOR},
    )
    assert _walk_collector_solo_defect(pair) is None

    # a brancher (b -> x, b -> y) makes the static pre-pass defer entirely,
    # even though z -> c leaves c with a single parent.
    with_brancher = _graph(
        [("b", "x"), ("b", "y"), ("z", "c")],
        {
            "b": Role.TRANSFORM,
            "x": Role.TRANSFORM,
            "y": Role.TRANSFORM,
            "z": Role.TRANSFORM,
            "c": Role.WALK_COLLECTOR,
        },
    )
    assert _walk_collector_solo_defect(with_brancher) is None
