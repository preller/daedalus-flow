"""Fixture-lab tests for the recipe loader, ordering and linearity checks.

Targets are imported inside each test; the in-memory unit tests are in test_recipe.py.
"""

from __future__ import annotations

import pytest

from tests._helpers import fixtures_root

_FIXTURE_LABS = fixtures_root() / "labs"
_BROKEN_LABS = fixtures_root() / "broken_labs"


def test_load_recipe_returns_typed_spec() -> None:
    """linear_smoke loads to a RecipeSpec with five typed RecipeModules in order."""
    from daedalus.core.recipe import load_recipe

    spec = load_recipe(_FIXTURE_LABS / "linear_smoke" / "lab.yaml")

    assert spec.name == "linear_smoke"
    ids = [m.id for m in spec.modules]
    assert ids == [
        "emit_ticks",
        "debug_io",
        "sleep_briefly",
        "summarize_walk",
        "collect_report",
    ]
    # depends are tuples of str; the emitter has none, each later step depends on
    # exactly its predecessor.
    by_id = {m.id: m for m in spec.modules}
    assert by_id["emit_ticks"].depends == ()
    assert by_id["debug_io"].depends == ("emit_ticks",)
    assert all(isinstance(d, str) for m in spec.modules for d in m.depends)


def test_load_recipe_parse_error_carries_problem_mark_line() -> None:
    """The fixture's error is on line 9; the reported line is an int, not None."""
    from daedalus.core.recipe import RecipeParseError, load_recipe

    with pytest.raises(RecipeParseError) as excinfo:
        load_recipe(_BROKEN_LABS / "unparseable.yaml")
    assert excinfo.value.line is not None
    assert isinstance(excinfo.value.line, int)


@pytest.mark.parametrize(
    "fixture, expected_leaf",
    [
        ("cyclic.yaml", "cycle"),
        ("dangling_dep.yaml", "dangling"),
        ("two_emitters.yaml", "two_emitters"),
    ],
)
def test_first_defect_preserves_broken_lab_classifications(
    fixture: str, expected_leaf: str
) -> None:
    """Each broken lab keeps its dae.lab.validate.* family token."""
    from daedalus.core.recipe import first_defect, load_recipe

    spec = load_recipe(_BROKEN_LABS / fixture)
    defect = first_defect(spec)
    assert defect is not None
    assert expected_leaf in defect


def test_execution_order_matches_linear_chain() -> None:
    """execution_order on linear_smoke is the lab.yaml chain order exactly."""
    from daedalus.core.recipe import execution_order, load_recipe

    spec = load_recipe(_FIXTURE_LABS / "linear_smoke" / "lab.yaml")
    assert execution_order(spec) == (
        "emit_ticks",
        "debug_io",
        "sleep_briefly",
        "summarize_walk",
        "collect_report",
    )


def test_linearity_defect_none_for_linear_smoke() -> None:
    """linear_smoke is linear, so linearity_defect returns None."""
    from daedalus.core.recipe import linearity_defect, load_recipe

    spec = load_recipe(_FIXTURE_LABS / "linear_smoke" / "lab.yaml")
    assert linearity_defect(spec) is None


def test_linearity_defect_names_offender_for_diamond() -> None:
    """Either seed (fan-out) or join (fan-in) may be named; both are offenders."""
    from daedalus.core.recipe import linearity_defect, load_recipe

    spec = load_recipe(_FIXTURE_LABS / "diamond_join" / "lab.yaml")
    defect = linearity_defect(spec)
    assert defect is not None
    assert ("join" in defect) or ("seed" in defect)


def test_read_module_role_reads_dae_module_yaml() -> None:
    """read_module_role returns the role string from a module's dae-module.yaml."""
    from daedalus.core.recipe import read_module_role

    emit_dir = _FIXTURE_LABS / "linear_smoke" / "modules" / "emit_ticks"
    assert read_module_role(emit_dir) == "emitter"


def test_build_plan_orders_steps_with_dirs_and_roles() -> None:
    """build_plan yields an ordered ExecutionPlan of PlanSteps with dir + role."""
    from daedalus.core.recipe import build_plan, load_recipe

    lab_dir = _FIXTURE_LABS / "linear_smoke"
    spec = load_recipe(lab_dir / "lab.yaml")
    plan = build_plan(spec, lab_dir)

    ids = [step.module_id for step in plan.steps]
    assert ids == [
        "emit_ticks",
        "debug_io",
        "sleep_briefly",
        "summarize_walk",
        "collect_report",
    ]
    first = plan.steps[0]
    assert first.index == 1
    assert first.role == "emitter"
    assert first.module_dir == lab_dir / "modules" / "emit_ticks"


def test_execution_order_raises_on_cycle() -> None:
    """A cyclic spec has no valid order, so execution_order raises."""
    from daedalus.core.recipe import execution_order, load_recipe

    spec = load_recipe(_BROKEN_LABS / "cyclic.yaml")
    with pytest.raises(Exception):  # noqa: B017,PT011 (any cycle error)
        execution_order(spec)
