"""Standalone runs of the five fixtures that ship committed goldens.

One test per role plus the diamond_join chain; outputs byte-equal expected/.
"""

import daedalus.flow as dae
from tests._helpers import assert_golden_json, fixtures_root, load_entry, run_module

MODULES = fixtures_root() / "modules"
LABS = fixtures_root() / "labs"


def test_role_vocabulary_is_collector():
    # Both convergence roles spell "collector" on disk and in the enum; the old
    # "aggregator" member names are gone.
    assert dae.Role.WALK_COLLECTOR.value == "walk_collector"
    assert dae.Role.FLIGHT_COLLECTOR.value == "flight_collector"
    assert not hasattr(dae.Role, "WALK_AGGREGATOR")
    assert not hasattr(dae.Role, "FLIGHT_AGGREGATOR")


def test_emit_pair(out_dir):
    mod = MODULES / "emit_pair"
    entry = load_entry(mod / "main.py")
    run_module(
        entry,
        role=dae.Role.EMITTER,
        output_dir=out_dir,
        input_dir=mod / "input",
    )
    assert_golden_json(out_dir / "roster.json", mod / "expected" / "roster.json")


def test_scale_series(out_dir):
    mod = MODULES / "scale_series"
    entry = load_entry(mod / "main.py")
    run_module(
        entry,
        role=dae.Role.TRANSFORM,
        output_dir=out_dir,
        input_dir=mod / "input",
    )
    assert_golden_json(out_dir / "scaled.json", mod / "expected" / "scaled.json")


def test_merge_walks(out_dir):
    mod = MODULES / "merge_walks"
    entry = load_entry(mod / "main.py")
    run_module(
        entry,
        role=dae.Role.WALK_COLLECTOR,
        output_dir=out_dir,
        walk_inputs={
            "walk_1": mod / "walk_inputs" / "walk_1",
            "walk_2": mod / "walk_inputs" / "walk_2",
        },
    )
    assert_golden_json(out_dir / "merged.json", mod / "expected" / "merged.json")


def test_reduce_flights(out_dir):
    mod = MODULES / "reduce_flights"
    entry = load_entry(mod / "main.py")
    run_module(
        entry,
        role=dae.Role.FLIGHT_COLLECTOR,
        output_dir=out_dir,
        flight_inputs={
            "flight_1": mod / "flight_inputs" / "flight_1",
            "flight_2": mod / "flight_inputs" / "flight_2",
        },
    )
    assert_golden_json(out_dir / "reduced.json", mod / "expected" / "reduced.json")


def test_diamond_join(tmp_path):
    # Modules run by hand through run_module and load_entry, no engine or CLI, as
    # the documented "modules run standalone" contract; distinct from the engine
    # and journey diamond_join coverage. join sums both branches, 11 + 101 = 112.
    lab = LABS / "diamond_join"
    mods = lab / "modules"

    seed_out = run_module(
        load_entry(mods / "seed" / "main.py"),
        role=dae.Role.TRANSFORM,
        output_dir=tmp_path / "seed",
        input_dir=lab / "input",
    )
    left_out = run_module(
        load_entry(mods / "left" / "main.py"),
        role=dae.Role.TRANSFORM,
        output_dir=tmp_path / "left",
        input_dir=seed_out,
    )
    right_out = run_module(
        load_entry(mods / "right" / "main.py"),
        role=dae.Role.TRANSFORM,
        output_dir=tmp_path / "right",
        input_dir=seed_out,
    )
    join_out = run_module(
        load_entry(mods / "join" / "main.py"),
        role=dae.Role.WALK_COLLECTOR,
        output_dir=tmp_path / "join",
        walk_inputs={"left": left_out, "right": right_out},
    )
    assert_golden_json(join_out / "joined.json", lab / "expected" / "joined.json")
