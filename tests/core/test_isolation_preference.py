"""Per-module isolation preference and lab isolation policy parsing.

A module preference is a value or a strongest-first ladder over none, uv and nix.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# --- lab policy: _parse_isolation and load_recipe_text


def test_lab_isolation_auto_parses() -> None:
    from daedalus.core.recipe import load_recipe_text

    spec = load_recipe_text("isolation: 'auto'\nmodules: []\n")
    assert spec.isolation == "auto"


@pytest.mark.parametrize("value", ["ambient", "uv", "nix"])
def test_lab_isolation_strategy_values_still_parse(value: str) -> None:
    from daedalus.core.recipe import load_recipe_text

    spec = load_recipe_text(f"isolation: {value}\nmodules: []\n")
    assert spec.isolation == value


def test_lab_isolation_unset_round_trips_to_none() -> None:
    from daedalus.core.recipe import load_recipe_text

    spec = load_recipe_text("modules: []\n")
    assert spec.isolation is None


def test_lab_isolation_fused_rejected_with_v2_pointer() -> None:
    from daedalus.core.recipe import RecipeParseError, load_recipe_text

    with pytest.raises(RecipeParseError, match="v2"):
        load_recipe_text("isolation: 'fused'\nmodules: []\n")


def test_lab_isolation_unknown_value_rejected() -> None:
    from daedalus.core.recipe import RecipeParseError, load_recipe_text

    with pytest.raises(RecipeParseError):
        load_recipe_text("isolation: 'nx'\nmodules: []\n")


def test_lab_isolation_ambient_with_parallel_still_rejected() -> None:
    """ambient is in-process and refuses max_workers > 1."""
    from daedalus.core.recipe import RecipeParseError, load_recipe_text

    with pytest.raises(RecipeParseError, match="max_workers"):
        load_recipe_text("isolation: 'ambient'\nmax_workers: 4\nmodules: []\n")


# --- module preference: _parse_isolation_pref


def test_pref_single_value_becomes_one_entry_ladder() -> None:
    from daedalus.core.recipe import _parse_isolation_pref

    assert _parse_isolation_pref("nix") == ("nix",)


def test_pref_omitted_defaults_to_none() -> None:
    from daedalus.core.recipe import _parse_isolation_pref

    assert _parse_isolation_pref(None) == ("none",)


def test_pref_ladder_strongest_first_parses() -> None:
    from daedalus.core.recipe import _parse_isolation_pref

    assert _parse_isolation_pref(["nix", "uv"]) == ("nix", "uv")
    assert _parse_isolation_pref(["nix", "uv", "none"]) == ("nix", "uv", "none")


def test_pref_rejects_unknown_value() -> None:
    from daedalus.core.recipe import RecipeParseError, _parse_isolation_pref

    with pytest.raises(RecipeParseError):
        _parse_isolation_pref("ambient")  # ambient is a lab strategy, not a module pref
    with pytest.raises(RecipeParseError):
        _parse_isolation_pref(["nix", "nope"])


def test_pref_rejects_out_of_order_ladder() -> None:
    """A ladder lists strengths strictly decreasing, strongest first."""
    from daedalus.core.recipe import RecipeParseError, _parse_isolation_pref

    with pytest.raises(RecipeParseError, match="order"):
        _parse_isolation_pref(["uv", "nix"])


def test_pref_rejects_duplicate_ladder_entry() -> None:
    from daedalus.core.recipe import RecipeParseError, _parse_isolation_pref

    with pytest.raises(RecipeParseError):
        _parse_isolation_pref(["nix", "nix"])


def test_pref_rejects_empty_ladder() -> None:
    from daedalus.core.recipe import RecipeParseError, _parse_isolation_pref

    with pytest.raises(RecipeParseError):
        _parse_isolation_pref([])


def test_pref_rejects_non_string_non_list() -> None:
    from daedalus.core.recipe import RecipeParseError, _parse_isolation_pref

    with pytest.raises(RecipeParseError):
        _parse_isolation_pref(3)


# --- module reader: read_module_isolation_pref


def test_read_module_pref_single_value(tmp_path: Path) -> None:
    from daedalus.core.recipe import read_module_isolation_pref

    (tmp_path / "dae-module.yaml").write_text("role: transform\nisolation: 'nix'\n")
    assert read_module_isolation_pref(tmp_path) == ("nix",)


def test_read_module_pref_ladder(tmp_path: Path) -> None:
    from daedalus.core.recipe import read_module_isolation_pref

    (tmp_path / "dae-module.yaml").write_text("role: transform\nisolation: [nix, uv]\n")
    assert read_module_isolation_pref(tmp_path) == ("nix", "uv")


def test_read_module_pref_absent_field_defaults_none(tmp_path: Path) -> None:
    from daedalus.core.recipe import read_module_isolation_pref

    (tmp_path / "dae-module.yaml").write_text("role: transform\n")
    assert read_module_isolation_pref(tmp_path) == ("none",)
