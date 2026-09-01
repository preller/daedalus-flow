"""Golden tests for the eight deterministic modules of the exoplanet_validation lab.

Each module runs standalone; the four sampler fits are in test_stochastic_fits.py.
"""

import itertools
import json
import math

import daedalus.flow as dae
from tests._helpers import (
    assert_golden_json,
    assert_golden_json_approx,
    fixtures_root,
    load_entry,
    run_module,
)

LAB = fixtures_root() / "labs" / "exoplanet_validation"
MODULES = LAB / "modules"


# --- seeded source chain: generate -> fetch -> denoise, bit-stable at seed 0


def test_generate_targets(out_dir):
    mod = MODULES / "generate_targets"
    entry = load_entry(mod / "main.py")
    run_module(
        entry,
        role=dae.Role.EMITTER,
        output_dir=out_dir,
        input_dir=LAB / "input",
    )
    produced = out_dir / "targets.json"
    roster = json.loads(produced.read_text())
    assert isinstance(roster, list) and len(roster) == 2
    assert [r["target"] for r in roster] == ["toi-1337b", "toi-1431b"]
    assert set(roster[0]) == {
        "target",
        "period_days",
        "rp_rstar",
        "duration_h",
        "snr",
    }
    assert_golden_json(produced, mod / "expected" / "targets.json")


def test_fetch_archive_data(tmp_path, out_dir):
    # generate_targets feeds fetch_archive_data; flight_1 selects roster index 0
    # (toi-1337b). Seed 0 noise makes the folded curve bit-stable.
    gen = MODULES / "generate_targets"
    gen_out = run_module(
        load_entry(gen / "main.py"),
        role=dae.Role.EMITTER,
        output_dir=tmp_path / "gen",
        input_dir=LAB / "input",
    )
    mod = MODULES / "fetch_archive_data"
    run_module(
        load_entry(mod / "main.py"),
        role=dae.Role.TRANSFORM,
        output_dir=out_dir,
        input_dir=gen_out,
        flight_id="flight_1",
        seed=0,
    )
    produced = out_dir / "folded.json"
    folded = json.loads(produced.read_text())
    assert set(folded) == {
        "target",
        "period_days",
        "phase",
        "flux",
        "flux_err",
        "true_depth",
        "true_duration_h",
        "rp_rstar",
        "a_rstar",
        "snr",
    }
    assert folded["target"] == "toi-1337b"
    # true_depth = rp_rstar**2 = 0.030**2 = 0.0009; true_duration_h = 3.0.
    assert folded["true_depth"] == 0.0009
    assert folded["true_duration_h"] == 3.0
    # phase and flux are computed floats, compared within tolerance.
    assert_golden_json_approx(produced, mod / "expected" / "folded.json")


def test_denoise_lightcurve(tmp_path, out_dir):
    # fetch_archive_data feeds denoise_lightcurve, which bins the folded curve with
    # lightkurve, 5 points per bin.
    gen_out = run_module(
        load_entry(MODULES / "generate_targets" / "main.py"),
        role=dae.Role.EMITTER,
        output_dir=tmp_path / "gen",
        input_dir=LAB / "input",
    )
    fetch_out = run_module(
        load_entry(MODULES / "fetch_archive_data" / "main.py"),
        role=dae.Role.TRANSFORM,
        output_dir=tmp_path / "fetch",
        input_dir=gen_out,
        flight_id="flight_1",
        seed=0,
    )
    mod = MODULES / "denoise_lightcurve"
    run_module(
        load_entry(mod / "main.py"),
        role=dae.Role.TRANSFORM,
        output_dir=out_dir,
        input_dir=fetch_out,
    )
    produced = out_dir / "denoised.json"
    denoised = json.loads(produced.read_text())
    assert "flux_denoised" in denoised
    assert set(denoised) == {
        "target",
        "period_days",
        "phase",
        "flux_denoised",
        "flux_err",
        "true_depth",
        "true_duration_h",
        "rp_rstar",
        "a_rstar",
        "snr",
    }
    # denoised phase and flux are computed floats, compared within tolerance.
    assert_golden_json_approx(produced, mod / "expected" / "denoised.json")


# --- collector and plot modules fed fixed synthetic posteriors; images are checked
# by presence and size only

# A small, fixed observed light curve shared by all four synthetic posteriors.
# plot_method_overlay reads observed.{phase,flux_denoised,flux_err} and rebuilds
# a batman model per method, so the grid must be a real (if tiny) phase grid.
_OBSERVED = {
    "phase": [round(-0.5 + i / 15.0, 4) for i in range(16)],
    "flux_denoised": [1.0] * 16,
    "flux_err": 0.0001,
}

# Sixteen fixed samples per parameter per method; no sampler runs.
_DEPTH_SAMPLES = {
    "nested": [0.0009 + 0.00001 * (i - 8) for i in range(16)],
    "mcmc": [0.00091 + 0.00001 * (i - 8) for i in range(16)],
    "gaussian": [0.00089 + 0.00001 * (i - 8) for i in range(16)],
    "biased": [0.0012 + 0.00002 * (i - 8) for i in range(16)],
}
_DURATION_SAMPLES = {
    "nested": [3.0 + 0.01 * (i - 8) for i in range(16)],
    "mcmc": [3.02 + 0.01 * (i - 8) for i in range(16)],
    "gaussian": [2.98 + 0.01 * (i - 8) for i in range(16)],
    "biased": [3.4 + 0.02 * (i - 8) for i in range(16)],
}
_DIAGNOSTICS = {
    "nested": {"criterion": "logz_err", "value": 0.42, "converged": True},
    "mcmc": {"criterion": "rhat_max", "value": 1.01, "converged": True},
    "gaussian": {"criterion": "cond_number", "value": 12.3, "converged": True},
    "biased": {"criterion": "logz_err", "value": 0.55, "converged": True},
}


def _mean_std(values):
    n = len(values)
    mean = sum(values) / n
    var = sum((v - mean) ** 2 for v in values) / n
    return mean, var**0.5


def _synthetic_posterior(method):
    """Build one synthetic posterior.json dict in the real fit schema."""
    depth = _DEPTH_SAMPLES[method]
    duration = _DURATION_SAMPLES[method]
    d_mean, d_std = _mean_std(depth)
    t_mean, t_std = _mean_std(duration)
    return {
        "method": method,
        "target": "toi-1337b",
        "depth": {"mean": d_mean, "std": d_std, "samples": depth},
        "duration_h": {"mean": t_mean, "std": t_std, "samples": duration},
        "diagnostics": _DIAGNOSTICS[method],
        "period_days": 6.0,
        "a_rstar": 15.0,
        "observed": _OBSERVED,
    }


_METHODS = ("nested", "mcmc", "gaussian", "biased")


def _stage_posteriors(stage):
    """Stage the 4 synthetic posteriors, one per walk dir; return walk_inputs."""
    walk_inputs = {}
    for i, method in enumerate(_METHODS, start=1):
        walk_id = f"walk_{i}"
        d = stage(walk_id, "posterior.json", _synthetic_posterior(method))
        walk_inputs[walk_id] = d
    return walk_inputs


def test_analyze_posterior_distances(stage, out_dir):
    # arrange: 4 synthetic posteriors, one per walk.
    walk_inputs = _stage_posteriors(stage)
    mod = MODULES / "analyze_posterior_distances"
    run_module(
        load_entry(mod / "main.py"),
        role=dae.Role.WALK_COLLECTOR,
        output_dir=out_dir,
        walk_inputs=walk_inputs,
    )
    produced = out_dir / "distances.json"
    distances = json.loads(produced.read_text())
    assert set(distances) == {"target", "methods", "pairwise"}
    assert distances["methods"] == sorted(_METHODS)
    # one entry per unordered method pair: C(len(_METHODS), 2), derived not hard-coded
    # so adding a fifth method updates the expectation instead of asserting "10 == 6".
    expected_pairs = len(list(itertools.combinations(_METHODS, 2)))
    assert "pairwise" in distances and len(distances["pairwise"]) == expected_pairs
    # pairwise wasserstein, energy, jensen_shannon and hellinger are computed floats.
    assert_golden_json_approx(produced, mod / "expected" / "distances.json")


def test_plot_joint_posteriors(stage, out_dir):
    walk_inputs = _stage_posteriors(stage)
    mod = MODULES / "plot_joint_posteriors"
    run_module(
        load_entry(mod / "main.py"),
        role=dae.Role.WALK_COLLECTOR,
        output_dir=out_dir,
        walk_inputs=walk_inputs,
    )
    # corner.png is present and non-empty; no pixel comparison.
    png = out_dir / "corner.png"
    assert png.exists() and png.stat().st_size > 0
    produced = out_dir / "corner_data.json"
    corner_data = json.loads(produced.read_text())
    assert set(corner_data) == {"target", "params", "methods", "per_method"}
    # per-method mean and std summaries are computed floats, compared within tolerance.
    assert_golden_json_approx(produced, mod / "expected" / "corner_data.json")


def test_plot_method_overlay(stage, out_dir):
    walk_inputs = _stage_posteriors(stage)
    mod = MODULES / "plot_method_overlay"
    run_module(
        load_entry(mod / "main.py"),
        role=dae.Role.WALK_COLLECTOR,
        output_dir=out_dir,
        walk_inputs=walk_inputs,
    )
    # overlay.png is present and non-empty; no pixel comparison.
    png = out_dir / "overlay.png"
    assert png.exists() and png.stat().st_size > 0
    produced = out_dir / "overlay_data.json"
    overlay_data = json.loads(produced.read_text())
    assert set(overlay_data) == {"target", "methods", "per_method"}
    # per-method rms and reduced_chi2 are computed floats, compared within tolerance.
    assert_golden_json_approx(produced, mod / "expected" / "overlay_data.json")


# The second flight's distances are the first flight's metric leaves scaled by this
# factor, so every cross_target abs_diff is a nonzero (1 - TARGET_2_SCALE) * v1.
TARGET_2_SCALE = 0.5
# distances.json pairwise carries 6 method-pairs x 2 params x 4 metrics = 48
# nonzero numeric metric leaves and 0 zero leaves, so scaling makes all 48
# cross_target abs_diff nonzero.
CROSS_TARGET_ROWS = 48
DISTANCE_PARAMS = ("depth", "duration_h")
DISTANCE_METRICS = ("wasserstein", "energy", "jensen_shannon", "hellinger")


def _scale_distance_metrics(distances, factor):
    """Copy of a distances dict with each pairwise metric leaf scaled by ``factor``."""
    scaled = json.loads(json.dumps(distances))
    for entry in scaled["pairwise"]:
        for param in DISTANCE_PARAMS:
            for metric in DISTANCE_METRICS:
                entry[param][metric] = entry[param][metric] * factor
    return scaled


def _stage_flight(stage, subdir, target, distances_golden):
    """Stage one flight dir with distances.json and placeholder carry files."""
    d = stage(subdir, "distances.json", json.loads(distances_golden.read_text()))
    for name in ("corner_data.json", "overlay_data.json"):
        (d / name).write_text(json.dumps({"target": target}, indent=2))
    for name in ("corner.png", "overlay.png"):
        (d / name).write_bytes(b"\x89PNG\r\n\x1a\n")
    return d


def test_compare_target_uncertainties(stage, out_dir):
    # Two flights, each keyed by its target via distances.json: the analyze golden
    # for one target and a scaled variant for the other.
    distances_golden = (
        MODULES / "analyze_posterior_distances" / "expected" / "distances.json"
    )
    d1 = _stage_flight(stage, "flight_1", "toi-1337b", distances_golden)
    # The second target is relabelled and every metric leaf scaled by TARGET_2_SCALE,
    # so the two targets differ everywhere; a relabel-only clone would make every
    # abs_diff zero.
    deep = _scale_distance_metrics(
        json.loads(distances_golden.read_text()), TARGET_2_SCALE
    )
    deep["target"] = "toi-1431b"
    d2 = stage("flight_2", "distances.json", deep)
    for name in ("corner_data.json", "overlay_data.json"):
        (d2 / name).write_text(json.dumps({"target": "toi-1431b"}, indent=2))
    for name in ("corner.png", "overlay.png"):
        (d2 / name).write_bytes(b"\x89PNG\r\n\x1a\n")

    mod = MODULES / "compare_target_uncertainties"
    run_module(
        load_entry(mod / "main.py"),
        role=dae.Role.FLIGHT_COLLECTOR,
        output_dir=out_dir,
        flight_inputs={"flight_1": d1, "flight_2": d2},
    )
    produced = out_dir / "comparison.json"
    comparison = json.loads(produced.read_text())
    assert set(comparison) == {"n_targets", "targets", "per_target", "cross_target"}
    assert comparison["targets"] == ["toi-1337b", "toi-1431b"]
    for target in comparison["targets"]:
        for name in ("distances.json", "corner.png", "overlay.png"):
            assert (out_dir / target / name).exists()

    # With target 2 scaled, every cross_target row has a nonzero abs_diff; the count
    # must equal the row count, not pass a soft threshold.
    cross_target = comparison["cross_target"]
    assert len(cross_target) == CROSS_TARGET_ROWS
    nonzero = sum(1 for row in cross_target if row["abs_diff"] > 0)
    assert nonzero == CROSS_TARGET_ROWS

    # Spot check of one row. The target-2 value is TARGET_2_SCALE times the target-1
    # value and abs_diff is |v1 - v2|.
    row = cross_target[0]
    v1 = row["per_target"]["toi-1337b"]
    v2 = row["per_target"]["toi-1431b"]
    assert math.isclose(v2, TARGET_2_SCALE * v1, rel_tol=1e-12)
    assert math.isclose(row["abs_diff"], abs(v1 - v2), rel_tol=1e-12)

    # cross_target abs_diff and the carried metrics are computed floats.
    assert_golden_json_approx(produced, mod / "expected" / "comparison.json")


def test_collect_results(tmp_path, stage, out_dir):
    # Stage the compare_target_uncertainties output layout (comparison.json plus
    # per-target carried subdirs) as the sole upstream of the sink.
    comparison_golden = (
        MODULES / "compare_target_uncertainties" / "expected" / "comparison.json"
    )
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    comparison = json.loads(comparison_golden.read_text())
    (upstream / "comparison.json").write_text(comparison_golden.read_text())
    for target in comparison["targets"]:
        tdir = upstream / target
        tdir.mkdir()
        for name in ("distances.json", "corner_data.json", "overlay_data.json"):
            (tdir / name).write_text(json.dumps({"target": target}, indent=2))
        for name in ("corner.png", "overlay.png"):
            (tdir / name).write_bytes(b"\x89PNG\r\n\x1a\n")

    mod = MODULES / "collect_results"
    run_module(
        load_entry(mod / "main.py"),
        role=dae.Role.TRANSFORM,
        output_dir=out_dir,
        input_dir=upstream,
    )
    # The results/ tree holds summary.json and the per-target carried files;
    # images are checked by presence only.
    results = out_dir / "results"
    assert (results / "summary.json").exists()
    for target in comparison["targets"]:
        for name in ("distances.json", "corner.png", "overlay.png"):
            assert (results / "targets" / target / name).exists()
    # summary carries the comparison floats forward, compared within tolerance.
    assert_golden_json_approx(
        results / "summary.json", mod / "expected" / "summary.json"
    )
