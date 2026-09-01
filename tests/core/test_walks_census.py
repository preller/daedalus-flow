"""Walk census on the shipped and inline labs.

Pure propagate pass, exact-value assertions, stdlib fixtures only.
"""

from __future__ import annotations

from pathlib import Path

from tests.core._walks_helpers import (
    _DEMO_LAB,
    _FIXTURE_LABS,
    _propagate_fixture,
    _propagate_inline,
)


def _modules_by_walk(plan: object) -> dict[str, set[str]]:
    """Map walk id -> the set of module ids instanced on that walk."""
    groups: dict[str, set[str]] = {}
    for instance in plan.instances:  # type: ignore[attr-defined]
        groups.setdefault(instance.walk_id, set()).add(instance.module_id)
    return groups


def test_exoplanet_census_is_five_walks_per_flight_no_w12() -> None:
    """w1..w6; the three sibling collectors all sit on w2 with one 4-entry map."""
    from daedalus.core.walks import WalkPlan, WalkRecord

    plan = _propagate_fixture(_FIXTURE_LABS / "exoplanet_validation")
    assert isinstance(plan, WalkPlan)

    assert [w.walk_id for w in plan.walks] == ["w1", "w2", "w3", "w4", "w5", "w6"]
    by_id = {w.walk_id: w for w in plan.walks}
    assert by_id["w1"] == WalkRecord("w1", None, None, None, None)
    assert by_id["w2"] == WalkRecord("w2", "f1", "w1", "generate_targets", None)
    assert by_id["w3"] == WalkRecord(
        "w3", "f1", "w2", "denoise_lightcurve", "fit_transit_biased"
    )
    assert by_id["w4"] == WalkRecord(
        "w4", "f1", "w2", "denoise_lightcurve", "fit_transit_gaussian"
    )
    assert by_id["w5"] == WalkRecord(
        "w5", "f1", "w2", "denoise_lightcurve", "fit_transit_mcmc"
    )
    assert by_id["w6"] == WalkRecord(
        "w6", "f1", "w2", "denoise_lightcurve", "fit_transit_nested"
    )

    collectors = {
        "analyze_posterior_distances",
        "plot_joint_posteriors",
        "plot_method_overlay",
    }
    collector_instances = {
        i.instance_id for i in plan.instances if i.module_id in collectors
    }
    assert collector_instances == {
        "analyze_posterior_distances@w2",
        "plot_joint_posteriors@w2",
        "plot_method_overlay@w2",
    }
    expected_inputs = {
        "w3": "fit_transit_biased@w3",
        "w4": "fit_transit_gaussian@w4",
        "w5": "fit_transit_mcmc@w5",
        "w6": "fit_transit_nested@w6",
    }
    for instance_id in sorted(collector_instances):
        assert plan.walk_inputs[instance_id] == expected_inputs


def test_diamond_join_census() -> None:
    """diamond_join: w1 (seed, join), w2 left, w3 right; join's group complete."""
    from daedalus.core.walks import WalkPlan, WalkRecord

    plan = _propagate_fixture(_FIXTURE_LABS / "diamond_join")
    assert isinstance(plan, WalkPlan)

    by_id = {w.walk_id: w for w in plan.walks}
    assert set(by_id) == {"w1", "w2", "w3"}
    assert by_id["w2"] == WalkRecord("w2", None, "w1", "seed", "left")
    assert by_id["w3"] == WalkRecord("w3", None, "w1", "seed", "right")
    assert _modules_by_walk(plan) == {
        "w1": {"seed", "join"},
        "w2": {"left"},
        "w3": {"right"},
    }
    # The collector fires once, back on the parent walk, mapping each child
    # walk id to its tail instance.
    assert plan.walk_inputs["join@w1"] == {"w2": "left@w2", "w3": "right@w3"}


def test_demo_census_m1() -> None:
    """demo at M=1: w1 global root, w2 flight root, w3 and w4 the sorted branches."""
    from daedalus.core.walks import WalkPlan

    plan = _propagate_fixture(_DEMO_LAB)
    assert isinstance(plan, WalkPlan)

    assert _modules_by_walk(plan) == {
        "w1": {"emit_targets", "summarize_population"},
        "w2": {"fetch_data", "compare_methods"},
        "w3": {"fit_mcmc"},
        "w4": {"fit_nested"},
    }
    by_id = {w.walk_id: w for w in plan.walks}
    # Successors sort, so mcmc comes before nested.
    assert by_id["w3"].branch_module == "fit_mcmc"
    assert by_id["w4"].branch_module == "fit_nested"


def test_linear_smoke_census() -> None:
    """An emitter gives a flight root walk; there is no collapse-to-bare case."""
    from daedalus.core.walks import WalkPlan

    plan = _propagate_fixture(_FIXTURE_LABS / "linear_smoke")
    assert isinstance(plan, WalkPlan)

    assert _modules_by_walk(plan) == {
        "w1": {"emit_ticks", "collect_report"},
        "w2": {"debug_io", "sleep_briefly", "summarize_walk"},
    }
    by_id = {w.walk_id: w for w in plan.walks}
    assert set(by_id) == {"w1", "w2"}
    assert by_id["w2"].flight_id == "f1"


def test_repeat_then_collect_is_legal_two_d_instances(tmp_path: Path) -> None:
    """d replicates per walk, one parent each; walk_inputs is keyed by walk id."""
    from daedalus.core.walks import WalkPlan

    plan = _propagate_inline(
        tmp_path,
        [
            ("seed", [], "transform"),
            ("left", ["seed"], "transform"),
            ("right", ["seed"], "transform"),
            ("d", ["left", "right"], "transform"),
            ("join", ["d"], "walk_collector"),
        ],
    )
    assert isinstance(plan, WalkPlan)

    d_instances = {i.instance_id for i in plan.instances if i.module_id == "d"}
    assert d_instances == {"d@w2", "d@w3"}
    d_indexes = {i.index for i in plan.instances if i.module_id == "d"}
    assert d_indexes == {4}
    # Each d instance has exactly one on-walk parent: non-blocking.
    assert [e for e in plan.edges if e[1] == "d@w2"] == [("left@w2", "d@w2")]
    assert [e for e in plan.edges if e[1] == "d@w3"] == [("right@w3", "d@w3")]
    assert plan.walk_inputs["join@w1"] == {"w2": "d@w2", "w3": "d@w3"}


def test_diamond_repeat_census_terminal_walks(tmp_path: Path) -> None:
    """Uncollected sibling groups are legal; both branch walks end at their own d."""
    from daedalus.core.walks import WalkPlan

    plan = _propagate_inline(
        tmp_path,
        [
            ("seed", [], "transform"),
            ("left", ["seed"], "transform"),
            ("right", ["seed"], "transform"),
            ("d", ["left", "right"], "transform"),
        ],
    )
    assert isinstance(plan, WalkPlan)

    assert [w.walk_id for w in plan.walks] == ["w1", "w2", "w3"]
    assert {i.instance_id for i in plan.instances if i.module_id == "d"} == {
        "d@w2",
        "d@w3",
    }
    assert set(plan.terminal) == {"d@w2", "d@w3"}
