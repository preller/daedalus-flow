"""Refusal tests for the walk-shape suite, over broken_labs and inline labs.

Each must-refuse lab is checked on validate (the defect token) and on run (invalid).
"""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

import pytest

from tests._helpers import fixtures_root
from tests.core._walk_shapes import _run_cli_in

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.integration  # validates and runs the engine over 23 shapes

_BROKEN_LABS = fixtures_root() / "broken_labs"

# Each must-refuse fixture under broken_labs/ and its dae.lab.validate.<token>.
# A lab refused with another code fails, and a lab that runs fails; both
# surfaces are asserted on the full code, never a substring.
_REFUSALS: dict[str, str] = {
    "partial_group": "dae.lab.validate.collector_incomplete_group",
    "cross_brancher_merge": "dae.lab.validate.collector_incomplete_group",
    "cross_level_merge": "dae.lab.validate.collector_incomplete_group",
    "collector_no_walks": "dae.lab.validate.collector_no_walks",
    "walks_reach_fc": "dae.lab.validate.walks_reach_flight_collector",
    "emitter_fanout": "dae.lab.validate.emitter_multi_successor",
    "budget_blowup": "dae.lab.validate.walk_budget_exceeded",
    "bad_module_id": "dae.lab.validate.reserved_separator_in_id",
    # The `complex` example's cross-cutting cases, gather without merge. Both reduce
    # to collector_incomplete_group: two collectors over a partial split of one
    # brancher's group, and one walk fed to two collectors (future walk_aggregator).
    "complex_partial_xy": "dae.lab.validate.collector_incomplete_group",
    "complex_into_two_collectors": "dae.lab.validate.collector_incomplete_group",
}


# --- must-refuse fixtures (broken_labs/)


def _copy_broken(name: str, dest_parent: Path) -> Path:
    """Copy a fixtures/broken_labs/<name> tree into ``dest_parent``."""
    dest = dest_parent / name
    shutil.copytree(
        _BROKEN_LABS / name, dest, ignore=shutil.ignore_patterns("__pycache__")
    )
    return dest


def _write_inline_lab(lab_dir: Path, name: str, modules: list[tuple]) -> None:
    """Write a role-bearing lab from (id, role, deps) tuples."""
    lines = [f"name: {name}", "modules:"]
    for mid, role, deps in modules:
        lines.append(f"  - id: {mid}")
        if deps:
            lines.append(f"    depends: [{', '.join(deps)}]")
        mdir = lab_dir / "modules" / mid
        mdir.mkdir(parents=True, exist_ok=True)
        (mdir / "dae-module.yaml").write_text(f"role: {role}\n")
    (lab_dir / "lab.yaml").write_text("\n".join(lines) + "\n")


@pytest.mark.parametrize("name", sorted(_REFUSALS))
def test_refusal_chain(name: str, tmp_path: Path) -> None:
    """validate returns the fixture's token; run refuses as invalid."""
    copy = _copy_broken(name, tmp_path)
    assert _run_cli_in(copy, "lab", "validate") == (1, _REFUSALS[name])
    assert _run_cli_in(copy, "lab", "run") == (2, "dae.lab.run.invalid")


def _chained_diamonds(lab_dir: Path, name: str, depth: int) -> None:
    """``depth`` chained diamonds: 2**depth configurations but linear instances."""
    modules: list[tuple] = [("src", "transform", [])]
    prev = "src"
    for k in range(depth):
        g, a, b, j = f"g{k:02d}", f"a{k:02d}", f"b{k:02d}", f"j{k:02d}"
        modules += [
            (g, "transform", [prev]),
            (a, "transform", [g]),
            (b, "transform", [g]),
            (j, "walk_collector", [a, b]),
        ]
        prev = j
    modules.append(("snk", "transform", [prev]))
    _write_inline_lab(lab_dir, name, modules)


def test_config_walk_budget_refuses_independently_of_instance_budget(
    tmp_path: Path,
) -> None:
    """Depth 9 gives 512 configurations but only 38 run-once instances."""
    from daedalus.core import walks
    from daedalus.core.recipe import load_recipe

    lab = tmp_path / "config_blowup"
    _chained_diamonds(lab, "config_blowup", 9)

    assert _run_cli_in(lab, "lab", "validate") == (
        1,
        "dae.lab.validate.config_walk_budget_exceeded",
    )
    assert _run_cli_in(lab, "lab", "run") == (2, "dae.lab.run.invalid")

    defect = walks.propagate(load_recipe(lab / "lab.yaml"), lab)
    assert isinstance(defect, walks.WalkDefect)
    assert defect.token == "config_walk_budget_exceeded"  # noqa: S105 (defect token)
    assert "512" in defect.reason
    assert "256" in defect.reason

    plan = walks.propagate(load_recipe(lab / "lab.yaml"), lab, config_budget=10_000)
    assert isinstance(plan, walks.WalkPlan)
    # The same depth-9 shape has 512 configurations yet 38 run-once instances
    # (src, snk and 4 per diamond): the collectors keep the instance count linear.
    # An exact 38 fails as soon as the census stops being linear in the depth.
    assert len(plan.instances) == 38
    assert len(plan.instances) < walks.DEFAULT_WALK_BUDGET
    assert len(walks.configurations(plan)) == 512


def test_bad_module_id_visualize_surfaces_verdict_not_traceback(
    tmp_path: Path,
) -> None:
    """Visualize on a reserved-separator lab returns the verdict, not a crash."""
    copy = _copy_broken("bad_module_id", tmp_path)
    assert _run_cli_in(copy, "lab", "visualize") == (
        1,
        "dae.lab.validate.reserved_separator_in_id",
    )


def test_boundary_brancherless_chain_still_walk_collector_solo(
    tmp_path: Path,
) -> None:
    """A brancherless in-degree-1 chain still trips the static pre-pass."""
    copy = _copy_broken("walk_collector_solo", tmp_path)
    assert _run_cli_in(copy, "lab", "validate") == (
        1,
        "dae.lab.validate.walk_collector_solo",
    )


def test_first_defect_separator_beats_incomplete_group(tmp_path: Path) -> None:
    """A lab with both defects reports reserved_separator_in_id."""
    lab = tmp_path / "sep_and_group"
    _write_inline_lab(
        lab,
        "sep_and_group",
        [
            ("src", "transform", []),
            ("a", "transform", ["src"]),
            ("b", "transform", ["src"]),
            ("c@x", "transform", ["src"]),
            ("join", "walk_collector", ["a", "b"]),
        ],
    )
    assert _run_cli_in(lab, "lab", "validate") == (
        1,
        "dae.lab.validate.reserved_separator_in_id",
    )


def test_first_defect_cycle_beats_incomplete_group(tmp_path: Path) -> None:
    """first_defect reports the cycle before the token pass runs."""
    lab = tmp_path / "cycle_and_group"
    _write_inline_lab(
        lab,
        "cycle_and_group",
        [
            ("src", "transform", ["join"]),
            ("a", "transform", ["src"]),
            ("b", "transform", ["src"]),
            ("join", "walk_collector", ["a", "b"]),
        ],
    )
    assert _run_cli_in(lab, "lab", "validate") == (1, "dae.lab.validate.cycle")
