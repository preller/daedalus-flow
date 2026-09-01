"""Pure, host-independent resolution of each module's isolation strategy.

``resolve_plan`` maps each ``ModuleEnv`` against the lab policy and ``max_workers``.
"""

from __future__ import annotations

import pytest


def _env(module: str = "m", preference=("none",), **files):
    from daedalus.core.engine.isolation import ModuleEnv

    return ModuleEnv(module=module, preference=tuple(preference), **files)


def test_auto_single_nix_pref_with_own_flake() -> None:
    from daedalus.core.engine.isolation import resolve_module

    r = resolve_module(_env(preference=("nix",), has_flake=True), "auto", 1)
    assert (r.strategy, r.downgraded, r.source, r.flake_origin) == (
        "nix",
        False,
        "preference",
        "own-flake",
    )


def test_auto_nix_pref_with_lock_is_auto_gen() -> None:
    from daedalus.core.engine.isolation import resolve_module

    r = resolve_module(_env(preference=("nix",), has_lock=True), "auto", 1)
    assert r.strategy == "nix"
    assert r.flake_origin == "generated-from-lock"
    assert r.source == "auto-gen"


def test_auto_uv_preference() -> None:
    from daedalus.core.engine.isolation import resolve_module

    r = resolve_module(_env(preference=("uv",), has_requirements=True), "auto", 1)
    assert (r.strategy, r.downgraded, r.source, r.flake_origin) == (
        "uv",
        False,
        "preference",
        None,
    )


def test_auto_none_pref_serial_is_ambient() -> None:
    from daedalus.core.engine.isolation import resolve_module

    assert resolve_module(_env(preference=("none",)), "auto", 1).strategy == "ambient"


def test_auto_none_pref_parallel_is_uv() -> None:
    from daedalus.core.engine.isolation import resolve_module

    assert resolve_module(_env(preference=("none",)), "auto", 4).strategy == "uv"


def test_unset_policy_matches_auto_for_none_pref_d16() -> None:
    """None (unset) preserves the default exactly: K=1 ambient, K>1 uv."""
    from daedalus.core.engine.isolation import resolve_module

    assert resolve_module(_env(preference=("none",)), None, 1).strategy == "ambient"
    assert resolve_module(_env(preference=("none",)), None, 4).strategy == "uv"


def test_auto_ladder_falls_to_satisfiable_entry() -> None:
    """[uv, none] with no env files: uv unbacked, sanctioned none fallback (ambient)."""
    from daedalus.core.engine.isolation import resolve_module

    r = resolve_module(_env(preference=("uv", "none")), "auto", 1)
    assert r.strategy == "ambient"  # none realized at K=1
    assert r.downgraded is False  # none is in the ladder, a sanctioned fallback
    assert r.source == "preference"


def test_auto_nix_pref_backed_by_requirements_generates() -> None:
    """nix's backing is a superset of uv's: a [nix, uv] + requirements picks nix."""
    from daedalus.core.engine.isolation import resolve_module

    r = resolve_module(_env(preference=("nix", "uv"), has_requirements=True), "auto", 1)
    assert r.strategy == "nix"
    assert r.flake_origin == "generated-from-requirements"


def test_lab_uv_forces_single_nix_to_uv_downgraded() -> None:
    from daedalus.core.engine.isolation import resolve_module

    r = resolve_module(_env(preference=("nix",), has_flake=True), "uv", 4)
    assert r.strategy == "uv"
    assert r.downgraded is True  # nix-only preference, no sanctioned uv fallback
    assert r.source == "policy"


def test_lab_uv_ladder_nix_uv_is_sanctioned_not_downgraded() -> None:
    from daedalus.core.engine.isolation import resolve_module

    r = resolve_module(
        _env(preference=("nix", "uv"), has_flake=True, has_requirements=True), "uv", 4
    )
    assert r.strategy == "uv"
    assert r.downgraded is False  # uv is in the ladder, so sanctioned


def test_lab_ambient_on_uv_pref_is_downgrade() -> None:
    from daedalus.core.engine.isolation import resolve_module

    r = resolve_module(_env(preference=("uv",), has_requirements=True), "ambient", 1)
    assert r.strategy == "ambient"
    assert r.downgraded is True


def test_lab_uv_on_none_pref_is_not_a_downgrade() -> None:
    from daedalus.core.engine.isolation import resolve_module

    r = resolve_module(_env(preference=("none",)), "uv", 4)
    assert r.strategy == "uv"
    assert r.downgraded is False  # forcing up is never a downgrade


def test_lab_nix_prefers_own_flake() -> None:
    from daedalus.core.engine.isolation import resolve_module

    r = resolve_module(
        _env(preference=("none",), has_flake=True, has_lock=True), "nix", 4
    )
    assert r.strategy == "nix"
    assert r.flake_origin == "own-flake"
    assert r.source == "policy"  # own flake, not auto-generated


def test_lab_nix_generates_from_lock() -> None:
    from daedalus.core.engine.isolation import resolve_module

    r = resolve_module(_env(preference=("none",), has_lock=True), "nix", 4)
    assert r.strategy == "nix"
    assert r.flake_origin == "generated-from-lock"
    assert r.source == "auto-gen"


def test_lab_nix_nothing_to_nixify_has_null_flake_origin() -> None:
    """A stdlib-only module forced to nix: null flake_origin is the error case."""
    from daedalus.core.engine.isolation import resolve_module

    r = resolve_module(_env(preference=("none",)), "nix", 4)
    assert r.strategy == "nix"
    assert r.flake_origin is None


def test_lab_nix_requirements_only_generates() -> None:
    """A requirements-only module forced to nix is generated from them."""
    from daedalus.core.engine.isolation import resolve_module

    r = resolve_module(_env(preference=("none",), has_requirements=True), "nix", 4)
    assert r.strategy == "nix"
    assert r.flake_origin == "generated-from-requirements"
    assert r.source == "auto-gen"


def test_resolve_plan_heterogeneous_preserves_order() -> None:
    from daedalus.core.engine.isolation import resolve_plan

    envs = [
        _env("fit", preference=("nix",), has_flake=True),
        _env("clean", preference=("uv",), has_requirements=True),
        _env("plot", preference=("none",)),
    ]
    plan = resolve_plan(envs, "auto", 1)
    assert [r.module for r in plan] == ["fit", "clean", "plot"]
    assert [r.strategy for r in plan] == ["nix", "uv", "ambient"]


def test_resolution_is_deterministic_and_host_independent() -> None:
    """No host argument exists; the same inputs always resolve identically."""
    from daedalus.core.engine.isolation import resolve_module

    env = _env(preference=("nix",), has_flake=True)
    assert resolve_module(env, "auto", 1) == resolve_module(env, "auto", 1)


def test_strategy_for_maps_names_to_strategy_instances() -> None:
    from daedalus.core.engine.isolation import (
        AmbientStrategy,
        NixStrategy,
        UvStrategy,
        strategy_for,
    )

    assert isinstance(strategy_for("ambient"), AmbientStrategy)
    assert isinstance(strategy_for("uv"), UvStrategy)
    assert isinstance(strategy_for("nix"), NixStrategy)
    with pytest.raises(ValueError, match="unknown isolation strategy"):
        strategy_for("bogus")
