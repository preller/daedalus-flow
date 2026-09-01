"""Unit tests for the recipe loader, execution order, linearity and seed derivation.

Each test imports its target inside the body so collection stays cheap.
"""

from __future__ import annotations

from pathlib import Path

import pytest


def test_load_recipe_text_parses_max_workers() -> None:
    from daedalus.core.recipe import load_recipe_text

    spec = load_recipe_text("name: 'x'\nmax_workers: 4\nmodules:\n  - id: seed\n")

    assert spec.max_workers == 4


def test_load_recipe_text_max_workers_defaults_to_1() -> None:
    from daedalus.core.recipe import load_recipe_text

    spec = load_recipe_text("name: 'x'\nmodules:\n  - id: seed\n")

    assert spec.max_workers == 1


def test_load_recipe_text_rejects_non_int_max_workers() -> None:
    from daedalus.core.recipe import RecipeParseError, load_recipe_text

    with pytest.raises(RecipeParseError):
        load_recipe_text("name: 'x'\nmax_workers: two\nmodules:\n  - id: seed\n")


def test_load_recipe_text_rejects_bool_max_workers() -> None:
    """YAML `true` is a bool, an int subclass; the loader still rejects it."""
    from daedalus.core.recipe import RecipeParseError, load_recipe_text

    with pytest.raises(RecipeParseError):
        load_recipe_text("name: 'x'\nmax_workers: true\nmodules:\n  - id: seed\n")


def test_load_recipe_text_rejects_non_positive_max_workers() -> None:
    from daedalus.core.recipe import RecipeParseError, load_recipe_text

    for bad in (0, -1):
        with pytest.raises(RecipeParseError):
            load_recipe_text(f"name: 'x'\nmax_workers: {bad}\nmodules:\n  - id: seed\n")


def test_load_recipe_text_parses_engine() -> None:
    from daedalus.core.recipe import load_recipe_text

    spec = load_recipe_text("name: 'x'\nengine: 'prefect'\nmodules:\n  - id: seed\n")

    assert spec.engine == "prefect"


def test_load_recipe_text_engine_defaults_to_local() -> None:
    from daedalus.core.recipe import load_recipe_text

    spec = load_recipe_text("name: 'x'\nmodules:\n  - id: seed\n")

    assert spec.engine == "local"


def test_load_recipe_text_rejects_unknown_engine() -> None:
    from daedalus.core.recipe import RecipeParseError, load_recipe_text

    with pytest.raises(RecipeParseError):
        load_recipe_text("name: 'x'\nengine: 'bogus'\nmodules:\n  - id: seed\n")


def test_load_recipe_text_rejects_non_string_engine() -> None:
    from daedalus.core.recipe import RecipeParseError, load_recipe_text

    with pytest.raises(RecipeParseError):
        load_recipe_text("name: 'x'\nengine: 3\nmodules:\n  - id: seed\n")


def test_load_recipe_text_rejects_non_string_bool_id() -> None:
    """YAML 1.1 reads `yes` as True; an id must be a string."""
    from daedalus.core.recipe import RecipeParseError, load_recipe_text

    with pytest.raises(RecipeParseError):
        load_recipe_text("name: 'x'\nmodules:\n  - id: yes\n")


def test_load_recipe_text_rejects_non_string_int_id() -> None:
    from daedalus.core.recipe import RecipeParseError, load_recipe_text

    with pytest.raises(RecipeParseError):
        load_recipe_text("name: 'x'\nmodules:\n  - id: 1\n")


def test_load_recipe_text_rejects_duplicate_ids() -> None:
    from daedalus.core.recipe import RecipeParseError, load_recipe_text

    with pytest.raises(RecipeParseError):
        load_recipe_text("name: 'x'\nmodules:\n  - id: a\n  - id: a\n")


def test_load_recipe_text_rejects_bare_scalar_document() -> None:
    """safe_load returns the bare string without error; the loader raises."""
    from daedalus.core.recipe import RecipeParseError, load_recipe_text

    with pytest.raises(RecipeParseError):
        load_recipe_text("just a string\n")


def test_load_recipe_text_empty_document_is_empty_spec() -> None:
    from daedalus.core.recipe import load_recipe_text

    spec = load_recipe_text("")
    assert spec.modules == ()


def test_load_recipe_text_empty_depends_is_empty_tuple() -> None:
    """An empty `depends:` arrives from YAML as None."""
    from daedalus.core.recipe import load_recipe_text

    spec = load_recipe_text("modules:\n  - id: a\n    depends:\n")
    (module,) = spec.modules
    assert module.depends == ()


def test_execution_order_breaks_ties_by_sorted_str_not_insertion() -> None:
    """'10', '2', '1' order as 1, 10, 2; insertion-order ties would give 10, 2, 1."""
    from daedalus.core.recipe import execution_order, load_recipe_text

    spec = load_recipe_text("modules:\n  - id: '10'\n  - id: '2'\n  - id: '1'\n")
    assert execution_order(spec) == ("1", "10", "2")


def test_detached_two_cycle_is_invalid_cycle_not_unsupported() -> None:
    """a->b plus a detached c<->d passes the bare linearity predicate; cycle wins."""
    from daedalus.core.recipe import first_defect, load_recipe_text

    spec = load_recipe_text(
        "modules:\n"
        "  - id: a\n"
        "  - id: b\n    depends: [a]\n"
        "  - id: c\n    depends: [d]\n"
        "  - id: d\n    depends: [c]\n"
    )
    defect = first_defect(spec)
    assert defect is not None
    assert "cycle" in defect


def test_empty_spec_is_not_linear() -> None:
    from daedalus.core.recipe import linearity_defect, load_recipe_text

    spec = load_recipe_text("modules: []\n")
    assert linearity_defect(spec) is not None


def test_single_isolated_module_is_linear() -> None:
    from daedalus.core.recipe import linearity_defect, load_recipe_text

    spec = load_recipe_text("modules:\n  - id: solo\n")
    assert linearity_defect(spec) is None


def _scaffold_single_module_lab(tmp_path: Path, role: str) -> Path:
    """Write a one-module lab (id: solo) whose dae-module.yaml declares ``role``."""
    lab_dir = tmp_path / "lab"
    module_dir = lab_dir / "modules" / "solo"
    module_dir.mkdir(parents=True)
    (lab_dir / "lab.yaml").write_text("name: 'solo_lab'\nmodules:\n  - id: solo\n")
    (module_dir / "dae-module.yaml").write_text(f"role: {role}\n")
    (module_dir / "main.py").write_text("")
    return lab_dir


def test_build_plan_accepts_transform_source(tmp_path: Path) -> None:
    """The emitter role is available for the source, not required."""
    from daedalus.core.recipe import build_plan, load_recipe

    lab_dir = _scaffold_single_module_lab(tmp_path, "transform")
    spec = load_recipe(lab_dir / "lab.yaml")
    plan = build_plan(spec, lab_dir)
    assert [s.role for s in plan.steps] == ["transform"]


@pytest.mark.parametrize("role", ["walk_collector", "flight_collector"])
def test_build_plan_refuses_collector_source(tmp_path: Path, role: str) -> None:
    """Refused at plan time, before a run with empty walk_inputs or flight_inputs."""
    from daedalus.core.recipe import RecipeParseError, build_plan, load_recipe

    lab_dir = _scaffold_single_module_lab(tmp_path, role)
    spec = load_recipe(lab_dir / "lab.yaml")
    with pytest.raises(RecipeParseError, match="a collector cannot be the source"):
        build_plan(spec, lab_dir)


def test_derive_seed_golden_values() -> None:
    """Literal goldens; recomputing the hash here would miss a changed derivation."""
    from daedalus.core.engine.step import derive_seed

    # sha256(f"{flow_seed}:{step_id}"), first four bytes big-endian. Regenerate with
    # python -c "import hashlib; print(int.from_bytes(
    #   hashlib.sha256(b'0:emit_ticks').digest()[:4], 'big'))"
    goldens = {"0:emit_ticks": 3932580969}
    goldens["0:collect_report"] = 1846515381
    goldens["42:emit_ticks"] = 1322509034
    for key, expected_seed in goldens.items():
        flow_seed, step_id = key.split(":")
        assert derive_seed(int(flow_seed), step_id) == expected_seed
    # different step ids under the same flow seed derive different per-step seeds
    assert derive_seed(0, "emit_ticks") != derive_seed(0, "debug_io")


# lab.yaml spells the per-module role `role:`, the same key dae-module.yaml uses;
# the old `type:` key has no alias. On the run path (build_plan) the lab role
# overrides the dae-module.yaml role; the emitter validate checks stay spec-based.


def test_lab_yaml_role_key_populates_recipemodule_role() -> None:
    from daedalus.core.recipe import load_recipe_text

    spec = load_recipe_text("name: 'x'\nmodules:\n  - id: e\n    role: emitter\n")
    assert spec.modules[0].role == "emitter"


def test_lab_yaml_legacy_type_key_is_ignored_no_alias() -> None:
    from daedalus.core.recipe import load_recipe_text

    spec = load_recipe_text("name: 'x'\nmodules:\n  - id: e\n    type: emitter\n")
    assert spec.modules[0].role is None


def _scaffold_module_lab_with_lab_role(
    tmp_path: Path, *, disk_role: str, lab_role: str | None
) -> Path:
    """One-module lab with ``disk_role`` on disk and ``lab_role`` in lab.yaml if set."""
    lab_dir = tmp_path / "lab"
    module_dir = lab_dir / "modules" / "solo"
    module_dir.mkdir(parents=True)
    lab_role_line = f"    role: {lab_role}\n" if lab_role is not None else ""
    (lab_dir / "lab.yaml").write_text(
        f"name: 'solo_lab'\nmodules:\n  - id: solo\n{lab_role_line}"
    )
    (module_dir / "dae-module.yaml").write_text(f"role: {disk_role}\n")
    (module_dir / "main.py").write_text("")
    return lab_dir


def test_build_plan_lab_role_overrides_module_role(tmp_path: Path) -> None:
    from daedalus.core.recipe import build_plan, load_recipe

    lab_dir = _scaffold_module_lab_with_lab_role(
        tmp_path, disk_role="transform", lab_role="emitter"
    )
    spec = load_recipe(lab_dir / "lab.yaml")
    plan = build_plan(spec, lab_dir)
    assert [s.role for s in plan.steps] == ["emitter"]


def test_build_plan_falls_back_to_module_role_when_lab_role_absent(
    tmp_path: Path,
) -> None:
    from daedalus.core.recipe import build_plan, load_recipe

    lab_dir = _scaffold_module_lab_with_lab_role(
        tmp_path, disk_role="transform", lab_role=None
    )
    spec = load_recipe(lab_dir / "lab.yaml")
    plan = build_plan(spec, lab_dir)
    assert [s.role for s in plan.steps] == ["transform"]


def test_build_plan_lab_role_used_when_module_role_absent(tmp_path: Path) -> None:
    from daedalus.core.recipe import build_plan, load_recipe

    lab_dir = tmp_path / "lab"
    module_dir = lab_dir / "modules" / "solo"
    module_dir.mkdir(parents=True)
    (lab_dir / "lab.yaml").write_text(
        "name: 'solo_lab'\nmodules:\n  - id: solo\n    role: transform\n"
    )
    (module_dir / "dae-module.yaml").write_text("# no role here\n")
    (module_dir / "main.py").write_text("")
    spec = load_recipe(lab_dir / "lab.yaml")
    plan = build_plan(spec, lab_dir)
    assert [s.role for s in plan.steps] == ["transform"]


def test_build_plan_rejects_unknown_lab_role(tmp_path: Path) -> None:
    """An out-of-set lab-declared role is refused at plan time, like a disk role."""
    from daedalus.core.recipe import RecipeParseError, build_plan, load_recipe

    lab_dir = _scaffold_module_lab_with_lab_role(
        tmp_path, disk_role="transform", lab_role="bogus_role"
    )
    spec = load_recipe(lab_dir / "lab.yaml")
    with pytest.raises(RecipeParseError, match="unknown role"):
        build_plan(spec, lab_dir)
