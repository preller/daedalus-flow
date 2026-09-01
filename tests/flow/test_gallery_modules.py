"""Byte-exact golden tests for the seven user-facing gallery modules.

Each module runs standalone; upstream inputs are rebuilt into tmp_path first.
"""

import json

import daedalus.flow as dae
from tests._helpers import (
    assert_golden_json,
    assert_golden_json_approx,
    examples_root,
    load_entry,
    run_module,
)

MINIMAL = examples_root() / "minimal"
DEMO = examples_root() / "demo"
DEMO_MODULES = DEMO / "modules"


def _keys(path):
    return set(json.loads(path.read_text()).keys())


def test_normalize(tmp_path):
    mod = MINIMAL / "modules" / "normalize"
    out = run_module(
        load_entry(mod / "main.py"),
        role=dae.Role.TRANSFORM,
        output_dir=tmp_path / "normalize",
        input_dir=MINIMAL / "input",
    )
    produced = out / "normalized.json"
    assert _keys(produced) == {
        "time_bjd",
        "flux_normalized",
        "median_flux",
        "n_points",
    }
    # flux_normalized is a computed float, compared within tolerance.
    assert_golden_json_approx(produced, mod / "expected" / "normalized.json")


def test_emit_targets(tmp_path):
    mod = DEMO_MODULES / "emit_targets"
    out = run_module(
        load_entry(mod / "main.py"),
        role=dae.Role.EMITTER,
        output_dir=tmp_path / "emit",
        input_dir=DEMO / "input",
    )
    produced = out / "targets.json"
    roster = json.loads(produced.read_text())
    assert isinstance(roster, list) and len(roster) == 3
    assert set(roster[0].keys()) == {
        "target",
        "period_days",
        "rp_rstar",
        "duration_h",
        "snr",
    }
    assert_golden_json(produced, mod / "expected" / "targets.json")


def _emit(tmp_path):
    """Run emit_targets into tmp_path and return its output dir."""
    mod = DEMO_MODULES / "emit_targets"
    return run_module(
        load_entry(mod / "main.py"),
        role=dae.Role.EMITTER,
        output_dir=tmp_path / "emit",
        input_dir=DEMO / "input",
    )


def _fetch(tmp_path, emit_out, flight_id):
    """Run fetch_data for one flight into tmp_path and return its output dir."""
    mod = DEMO_MODULES / "fetch_data"
    return run_module(
        load_entry(mod / "main.py"),
        role=dae.Role.TRANSFORM,
        output_dir=tmp_path / f"fetch_{flight_id}",
        input_dir=emit_out,
        flight_id=flight_id,
        seed=0,
    )


def test_fetch_data(tmp_path):
    mod = DEMO_MODULES / "fetch_data"
    emit_out = _emit(tmp_path)
    out = _fetch(tmp_path, emit_out, "flight_1")
    produced = out / "folded.json"
    assert _keys(produced) == {
        "target",
        "period_days",
        "phase",
        "flux",
        "flux_err",
        "half_width",
        "true_depth",
    }
    # phase and flux are computed floats, compared within tolerance.
    assert_golden_json_approx(produced, mod / "expected" / "folded.json")


def test_fit_nested(tmp_path):
    mod = DEMO_MODULES / "fit_nested"
    emit_out = _emit(tmp_path)
    folded = _fetch(tmp_path, emit_out, "flight_1")
    out = run_module(
        load_entry(mod / "main.py"),
        role=dae.Role.TRANSFORM,
        output_dir=tmp_path / "nested",
        input_dir=folded,
        flight_id="flight_1",
        seed=0,
    )
    produced = out / "posterior.json"
    assert _keys(produced) == {"method", "target", "depth"}
    assert json.loads(produced.read_text())["method"] == "nested"
    # depth mean, std and samples are computed floats, compared within tolerance.
    assert_golden_json_approx(produced, mod / "expected" / "posterior.json")


def test_fit_mcmc(tmp_path):
    mod = DEMO_MODULES / "fit_mcmc"
    emit_out = _emit(tmp_path)
    folded = _fetch(tmp_path, emit_out, "flight_1")
    out = run_module(
        load_entry(mod / "main.py"),
        role=dae.Role.TRANSFORM,
        output_dir=tmp_path / "mcmc",
        input_dir=folded,
        flight_id="flight_1",
        seed=0,
    )
    produced = out / "posterior.json"
    assert _keys(produced) == {"method", "target", "depth"}
    assert json.loads(produced.read_text())["method"] == "mcmc"
    # depth mean, std and samples are computed floats, compared within tolerance.
    assert_golden_json_approx(produced, mod / "expected" / "posterior.json")


def _fit_pair(tmp_path, folded, flight_id):
    """Run fit_nested and fit_mcmc on one folded curve; return their dirs."""
    nested = run_module(
        load_entry(DEMO_MODULES / "fit_nested" / "main.py"),
        role=dae.Role.TRANSFORM,
        output_dir=tmp_path / f"nested_{flight_id}",
        input_dir=folded,
        flight_id=flight_id,
        seed=0,
    )
    mcmc = run_module(
        load_entry(DEMO_MODULES / "fit_mcmc" / "main.py"),
        role=dae.Role.TRANSFORM,
        output_dir=tmp_path / f"mcmc_{flight_id}",
        input_dir=folded,
        flight_id=flight_id,
        seed=0,
    )
    return nested, mcmc


def _compare(tmp_path, nested, mcmc, flight_id):
    """Run compare_methods over a nested/mcmc walk pair; return its output dir."""
    return run_module(
        load_entry(DEMO_MODULES / "compare_methods" / "main.py"),
        role=dae.Role.WALK_COLLECTOR,
        output_dir=tmp_path / f"compare_{flight_id}",
        walk_inputs={"nested": nested, "mcmc": mcmc},
        flight_id=flight_id,
    )


def test_compare_methods(tmp_path):
    mod = DEMO_MODULES / "compare_methods"
    emit_out = _emit(tmp_path)
    folded = _fetch(tmp_path, emit_out, "flight_1")
    nested, mcmc = _fit_pair(tmp_path, folded, "flight_1")
    out = _compare(tmp_path, nested, mcmc, "flight_1")
    produced = out / "comparison.json"
    assert _keys(produced) == {
        "target",
        "wasserstein_depth",
        "hellinger_depth",
        "depth_abs_diff",
    }
    # wasserstein, hellinger and abs_diff are floats, compared within tolerance.
    assert_golden_json_approx(produced, mod / "expected" / "comparison.json")


def test_summarize_population(tmp_path):
    mod = DEMO_MODULES / "summarize_population"
    emit_out = _emit(tmp_path)
    # The full demo emits 3 flights; aggregate all of them so the population
    # summary matches the committed golden.
    flight_inputs = {}
    for fi in (1, 2, 3):
        flight_id = f"flight_{fi}"
        folded = _fetch(tmp_path, emit_out, flight_id)
        nested, mcmc = _fit_pair(tmp_path, folded, flight_id)
        flight_inputs[flight_id] = _compare(tmp_path, nested, mcmc, flight_id)

    out = run_module(
        load_entry(mod / "main.py"),
        role=dae.Role.FLIGHT_COLLECTOR,
        output_dir=tmp_path / "summary",
        flight_inputs=flight_inputs,
    )
    produced = out / "summary.json"
    assert _keys(produced) == {
        "n_targets",
        "mean_wasserstein_depth",
        "mean_hellinger_depth",
        "per_target",
    }
    assert json.loads(produced.read_text())["n_targets"] == 3
    # mean wasserstein, hellinger and the per-target metrics are computed floats.
    assert_golden_json_approx(produced, mod / "expected" / "summary.json")
