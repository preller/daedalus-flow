"""Validate reconciles per-module isolation and the ``--json`` resolution block.

Errors, WARN and INFO notes all project from the resolved plan the payload carries.
"""

from __future__ import annotations

import shutil
from pathlib import Path

_FIXTURE_LABS = Path(__file__).resolve().parents[1] / "fixtures/labs"


def _pair(
    module: str = "m",
    preference=("none",),
    strategy: str = "ambient",
    downgraded: bool = False,
    source: str = "preference",
    flake_origin: str | None = None,
    **files: bool,
):
    from daedalus.core.engine.isolation import ModuleEnv, ModuleResolution

    env = ModuleEnv(module=module, preference=tuple(preference), **files)
    resolution = ModuleResolution(
        module=module,
        strategy=strategy,
        downgraded=downgraded,
        source=source,
        flake_origin=flake_origin,
    )
    return (env, resolution)


# --- errors


def test_unbacked_nix_preference_is_error() -> None:
    from daedalus.cli.commands.lab._validate import _isolation_error
    from daedalus.core.outcomes import Outcome

    pairs = [_pair(preference=("nix",), strategy="nix", flake_origin=None)]
    error = _isolation_error(pairs, "auto")
    assert error is not None
    assert error[0] == Outcome.DAE_LAB_VALIDATE_ISOLATION_UNBACKED


def test_nothing_to_nixify_under_lab_nix_is_error() -> None:
    from daedalus.cli.commands.lab._validate import _isolation_error
    from daedalus.core.outcomes import Outcome

    pairs = [_pair(preference=("none",), strategy="nix", flake_origin=None)]
    error = _isolation_error(pairs, "nix")
    assert error is not None
    assert error[0] == Outcome.DAE_LAB_VALIDATE_NOTHING_TO_NIXIFY


def test_unbacked_uv_preference_is_error() -> None:
    from daedalus.cli.commands.lab._validate import _isolation_error
    from daedalus.core.outcomes import Outcome

    pairs = [_pair(preference=("uv",), strategy="uv", source="preference")]
    error = _isolation_error(pairs, "auto")
    assert error is not None
    assert error[0] == Outcome.DAE_LAB_VALIDATE_ISOLATION_UNBACKED


def test_backed_nix_preference_is_not_an_error() -> None:
    from daedalus.cli.commands.lab._validate import _isolation_error

    pairs = [
        _pair(
            preference=("nix",),
            strategy="nix",
            flake_origin="own-flake",
            has_flake=True,
        )
    ]
    assert _isolation_error(pairs, "auto") is None


def test_uv_forced_by_policy_on_stdlib_module_is_not_an_error() -> None:
    from daedalus.cli.commands.lab._validate import _isolation_error

    # lab uv forcing a none-preference stdlib module: source=policy, not unbacked.
    pairs = [_pair(preference=("none",), strategy="uv", source="policy")]
    assert _isolation_error(pairs, "uv") is None


# --- advisories (WARN and INFO)


def test_downgrade_warning_predicts_the_late_failure() -> None:
    from daedalus.cli.commands.lab._validate import _isolation_advisories

    pairs = [
        _pair(
            preference=("nix",),
            strategy="uv",
            downgraded=True,
            source="policy",
            has_flake=True,
        )
    ]
    notes = _isolation_advisories(pairs)
    assert any("WARN" in n and "missing_package" in n for n in notes)


def test_sanctioned_ladder_fallback_does_not_warn() -> None:
    from daedalus.cli.commands.lab._validate import _isolation_advisories

    pairs = [
        _pair(
            preference=("nix", "uv"), strategy="uv", downgraded=False, source="policy"
        )
    ]
    assert _isolation_advisories(pairs) == []


def test_auto_gen_warning_lists_generated_modules() -> None:
    from daedalus.cli.commands.lab._validate import _isolation_advisories

    pairs = [
        _pair(
            module="fit",
            preference=("nix",),
            strategy="nix",
            source="auto-gen",
            flake_origin="generated-from-requirements",
            has_requirements=True,
        )
    ]
    notes = _isolation_advisories(pairs)
    assert any("auto-generated" in n and "fit" in n for n in notes)


def test_richer_files_emits_info() -> None:
    from daedalus.cli.commands.lab._validate import _isolation_advisories

    pairs = [_pair(preference=("none",), strategy="ambient", has_flake=True)]
    notes = _isolation_advisories(pairs)
    assert any("INFO" in n and "flake.nix" in n for n in notes)


# --- the --json resolution block


def test_isolation_resolution_block_for_sound_lab(tmp_path: Path) -> None:
    from daedalus.cli.commands.lab._validate import (
        _lab_resolution_pairs,
        isolation_resolution,
    )
    from daedalus.core.recipe import load_recipe

    lab = tmp_path / "diamond_join"
    shutil.copytree(_FIXTURE_LABS / "diamond_join", lab)
    spec = load_recipe(lab / "lab.yaml")
    block = isolation_resolution(_lab_resolution_pairs(spec, lab))

    assert block is not None
    assert {entry["module"] for entry in block} == {"seed", "left", "right", "join"}
    assert all(entry["strategy"] == "ambient" for entry in block)
    assert all(
        set(entry) == {"module", "strategy", "downgraded", "source", "flake_origin"}
        for entry in block
    )
