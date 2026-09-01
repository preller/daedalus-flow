"""Configuration walks, one complete source-to-sink path per user-facing walk.

The config blocks are hand-written and cross-checked against the on-disk tree.
"""

from __future__ import annotations

import re

import pytest

from tests.core._walk_shapes import _TREES, _WALK_LINES, _branch_walks, _plan

pytestmark = pytest.mark.integration  # validates and runs the engine over 23 shapes


# The user-facing walk is a configuration, a complete source-to-sink path with one
# choice per brancher and per sibling-collector set. The token-set walk_lines is
# the machine view and stays unchanged.


@pytest.mark.parametrize(
    ("name", "config_count"),
    [
        ("nested_join", 3),  # nested sub-branches collapse to leaves (token-set was 4)
        ("series_diamonds", 4),  # cartesian a1.b1.. (token-set was 4, but additive)
        ("mixed_collect", 3),  # uncollected-outer leaves (token-set was 4)
        ("sibling_collectors", 12),  # 4 fits x 3 sibling collectors (token-set was 4)
        ("wide4_join", 4),  # single region, config == token-set
        ("diamond_join", 2),  # single region, unchanged
    ],
)
def test_config_walk_count(name: str, config_count: int) -> None:
    """Configuration walks = source-to-sink paths; sibling sets are a choice."""
    from daedalus.core import walks

    assert len(walks.configurations(_plan(name))) == config_count


def test_complex_config_block_matches_the_spec() -> None:
    """48 walks in depth-first plan order; the journey tier pins the full block."""
    # The generic fixture (tests/fixtures/labs/complex), not the shipped example: the
    # integer labels come from lexicographical_topological_sort over the module ids
    # and are stable only against the module_A..module_AD ids.
    plan = _plan("complex")
    lines = plan.config_lines()
    assert lines[0] == (
        "Full:  1-2-{3-{5,6-10,7-11-{12,13}-(14)}-(16),4-{8,9-15}-(17)}-(18)"
        "-19-{20,21}-22-(23)-24-{25,26}-{(27),(28)}-[29]-30"
    )
    assert lines[1] == "Walks: 48"
    assert len(lines) == 50
    assert lines[2] == "  walk_1: 1-2-3-5-(16)-(18)-19-20-22-(23)-24-25-(27)-[29]-30"
    assert (
        lines[49] == "  walk_48: 1-2-4-9-15-(17)-(18)-19-21-22-(23)-24-26-(28)-[29]-30"
    )


# Config-walk blocks for the multi-region shapes (complex is pinned above). {} is a
# branch group, (N) a walk-collector closer, {(a),(b)} a sibling-collector set and
# [N] the flight-collector; sibling_collectors is a 3-way choice, 4 fits x 3 = 12.
_CONFIG_LINES: dict[str, tuple[str, ...]] = {
    "nested_join": (
        "Full:  1-{2-{4,5}-(6),3}-(7)",
        "Walks: 3",
        "  walk_1: 1-2-4-(6)-(7)",
        "  walk_2: 1-2-5-(6)-(7)",
        "  walk_3: 1-3-(7)",
    ),
    "series_diamonds": (
        "Full:  1-{2,3}-(4)-5-{6,7}-(8)",
        "Walks: 4",
        "  walk_1: 1-2-(4)-5-6-(8)",
        "  walk_2: 1-2-(4)-5-7-(8)",
        "  walk_3: 1-3-(4)-5-6-(8)",
        "  walk_4: 1-3-(4)-5-7-(8)",
    ),
    "mixed_collect": (
        "Full:  1-{2-{4,5}-(6),3}",
        "Walks: 3",
        "  walk_1: 1-2-4-(6)",
        "  walk_2: 1-2-5-(6)",
        "  walk_3: 1-3",
    ),
    "sibling_collectors": (
        "Full:  1-2-3-{4,5,6,7}-{(8),(9),(10)}-[11]-12",
        "Walks: 12",
        "  walk_1: 1-2-3-4-(8)-[11]-12",
        "  walk_2: 1-2-3-4-(9)-[11]-12",
        "  walk_3: 1-2-3-4-(10)-[11]-12",
        "  walk_4: 1-2-3-5-(8)-[11]-12",
        "  walk_5: 1-2-3-5-(9)-[11]-12",
        "  walk_6: 1-2-3-5-(10)-[11]-12",
        "  walk_7: 1-2-3-6-(8)-[11]-12",
        "  walk_8: 1-2-3-6-(9)-[11]-12",
        "  walk_9: 1-2-3-6-(10)-[11]-12",
        "  walk_10: 1-2-3-7-(8)-[11]-12",
        "  walk_11: 1-2-3-7-(9)-[11]-12",
        "  walk_12: 1-2-3-7-(10)-[11]-12",
    ),
}


def _disk_walk_modules(name: str) -> dict[str, list[str]]:
    """Per-walk module sequence from the ``_TREES`` golden, in step-number order."""
    step = re.compile(r"(?:^|/)walks/(walk_\d+)/(\d+)_(.+)$")
    by_walk: dict[str, list[tuple[int, str]]] = {}
    for rel in _TREES[name]:
        m = step.search(rel)
        if m is not None:
            by_walk.setdefault(m.group(1), []).append((int(m.group(2)), m.group(3)))
    return {wk: [mod for _, mod in sorted(steps)] for wk, steps in by_walk.items()}


def _config_line_modules(name: str) -> dict[str, list[str]]:
    """Per-walk module sequence implied by the hand-written ``_CONFIG_LINES``."""
    idx_to_mod = {i.index: i.module_id for i in _plan(name).instances}
    out: dict[str, list[str]] = {}
    for line in _CONFIG_LINES[name]:
        body = line.split(":", 1)
        if len(body) != 2 or not body[0].strip().startswith("walk_"):
            continue
        walk_id = body[0].strip()
        indices = [int(n) for n in re.findall(r"\d+", body[1])]
        out[walk_id] = [idx_to_mod[n] for n in indices]
    return out


@pytest.mark.parametrize("name", sorted(_CONFIG_LINES))
def test_runtime_tree_config_dirs_match_the_visualize_block(name: str) -> None:
    """_TREES is engine output; _CONFIG_LINES is hand-written, an independent check."""
    assert _disk_walk_modules(name) == _config_line_modules(name)


# The exoplanet shape at M=1 is the sibling_collectors topology and shares its
# visualize block. denoise_lightcurve is the brancher; its four method branches mint
# one walk each, the three sibling collectors and the flight collector mint none.
_EXOPLANET_BRANCH_MODULES = [
    "fit_transit_biased",
    "fit_transit_gaussian",
    "fit_transit_mcmc",
    "fit_transit_nested",
]
_EXOPLANET_COLLECTORS = {
    "plot_joint_posteriors",
    "analyze_posterior_distances",
    "plot_method_overlay",
    "compare_target_uncertainties",
}


def test_exoplanet_validation_token_census() -> None:
    """The exoplanet shape mints exactly 4 walks; the collectors mint zero."""
    plan = _plan("exoplanet_validation")

    # The visualize block is byte-exact against the shared sibling_collectors block.
    assert plan.walk_lines() == _WALK_LINES["sibling_collectors"]

    # Four branch walks, all born at the brancher, one per method.
    branch = _branch_walks(plan)
    assert len(branch) == 4
    assert {r.born_at for r in branch} == {"denoise_lightcurve"}
    assert sorted(r.branch_module for r in branch) == _EXOPLANET_BRANCH_MODULES

    # No walk is born at a collector; the walk-bearing sites are the root, the
    # emitter and the one brancher.
    born_at = {r.born_at for r in plan.walks}
    assert born_at & _EXOPLANET_COLLECTORS == set(), (
        f"a walk_collector minted a walk (born_at {born_at & _EXOPLANET_COLLECTORS})"
    )
    assert born_at == {None, "generate_targets", "denoise_lightcurve"}
