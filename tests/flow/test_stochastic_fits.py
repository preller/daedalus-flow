"""Recovery tests for the four sampler-backed fit modules of exoplanet_validation.

Sampler output is not bit-reproducible, so fits are checked against the truth.
"""

import json
import tempfile
from pathlib import Path

import pytest
from numpy.testing import assert_allclose

import daedalus.flow as dae
from tests._helpers import fixtures_root, load_entry, run_module

LAB = fixtures_root() / "labs" / "exoplanet_validation"
MODULES = LAB / "modules"

# Injected ground truth for toi-1337b (targets.csv row 1): rp_rstar=0.030 so
# true_depth = 0.030**2 = 0.0009, duration_h = 3.0. Signal to noise 9 makes it noisy.
TRUE_DEPTH = 0.0009
TRUE_DURATION_H = 3.0


@pytest.fixture(scope="module")
def denoised_input(tmp_path_factory):
    """Run generate -> fetch -> denoise once for toi-1337b at seed 0.

    Returns the directory holding ``denoised.json``; module scope so the chain
    runs a single time for the four fit tests.
    """
    base = tmp_path_factory.mktemp("denoised_input")

    targets_out = run_module(
        load_entry(MODULES / "generate_targets" / "main.py"),
        role=dae.Role.EMITTER,
        output_dir=base / "targets",
        input_dir=LAB / "input",
        flight_id="flight_1",
        seed=0,
    )
    folded_out = run_module(
        load_entry(MODULES / "fetch_archive_data" / "main.py"),
        role=dae.Role.TRANSFORM,
        output_dir=base / "folded",
        input_dir=targets_out,
        flight_id="flight_1",
        seed=0,
    )
    denoised_out = run_module(
        load_entry(MODULES / "denoise_lightcurve" / "main.py"),
        role=dae.Role.TRANSFORM,
        output_dir=base / "denoised",
        input_dir=folded_out,
        flight_id="flight_1",
        seed=0,
    )
    # The carried truths match the values derived from targets.csv.
    denoised = json.loads((denoised_out / "denoised.json").read_text())
    assert denoised["target"] == "toi-1337b"
    assert_allclose(denoised["true_depth"], TRUE_DEPTH)
    assert_allclose(denoised["true_duration_h"], TRUE_DURATION_H)
    return denoised_out


def assert_posterior_schema(post: dict) -> None:
    """Assert the fit posterior has the expected schema.

    depth and duration_h each carry mean, std and samples; the sample arrays are
    non-empty and at most 2000 long, since the dynesty-backed fits resample to at
    most 2000 equal-weight samples. diagnostics.converged is a bool.
    """
    for key in (
        "method",
        "target",
        "depth",
        "duration_h",
        "diagnostics",
        "period_days",
        "a_rstar",
        "observed",
    ):
        assert key in post, f"missing posterior key: {key}"

    for param in ("depth", "duration_h"):
        block = post[param]
        for sub in ("mean", "std", "samples"):
            assert sub in block, f"missing {param}.{sub}"
        n = len(block["samples"])
        assert 0 < n <= 2000, f"{param}.samples length out of bounds: {n}"

    diag = post["diagnostics"]
    for sub in ("criterion", "value", "converged"):
        assert sub in diag, f"missing diagnostics.{sub}"
    assert isinstance(diag["converged"], bool), "diagnostics.converged not a bool"


def recovered(post: dict) -> tuple[float, float]:
    """Return (depth_mean, duration_h_mean) from a fit posterior."""
    return (post["depth"]["mean"], post["duration_h"]["mean"])


def _run_fit(module_name: str, denoised_input):
    """Run a fit module standalone on the denoised input; return its posterior."""
    # A fresh dir per call keeps tests that run the same module independent.
    out = run_module(
        load_entry(MODULES / module_name / "main.py"),
        role=dae.Role.TRANSFORM,
        output_dir=Path(
            tempfile.mkdtemp(prefix=f"fit_{module_name}_", dir=denoised_input.parent)
        ),
        input_dir=denoised_input,
        flight_id="flight_1",
        seed=0,
    )
    return json.loads((out / "posterior.json").read_text())


# Calibrated by running each fit standalone at seed=0 on toi-1337b: the observed
# relative errors are about 0.01 to 0.02 for nested, mcmc and gaussian. 0.15 passes
# with margin and still fails a mean that is off by a factor of two.
R_DEPTH = 0.15
R_DUR = 0.15

# The mcmc chain is seeded, so its R-hat is deterministic at about 1.008. The bound
# sits just above it; the module's own RHAT_MAX=1.1 flag would only catch a chain
# that diverged badly.
RHAT_TIGHT = 1.02


@pytest.mark.slow
def test_nested_recovers_truth(denoised_input):
    post = _run_fit("fit_transit_nested", denoised_input)
    assert_posterior_schema(post)
    assert post["method"] == "nested"
    assert post["diagnostics"]["criterion"] == "logz_err"
    assert post["diagnostics"]["converged"] is True

    depth_mean, duration_mean = recovered(post)
    assert_allclose(depth_mean, TRUE_DEPTH, rtol=R_DEPTH)
    assert_allclose(duration_mean, TRUE_DURATION_H, rtol=R_DUR)


@pytest.mark.slow
def test_mcmc_recovers_truth(denoised_input):
    post = _run_fit("fit_transit_mcmc", denoised_input)
    assert_posterior_schema(post)
    assert post["method"] == "mcmc"
    assert post["diagnostics"]["criterion"] == "rhat_max"
    assert post["diagnostics"]["converged"] is True
    assert post["diagnostics"]["value"] < RHAT_TIGHT

    depth_mean, duration_mean = recovered(post)
    assert_allclose(depth_mean, TRUE_DEPTH, rtol=R_DEPTH)
    assert_allclose(duration_mean, TRUE_DURATION_H, rtol=R_DUR)


@pytest.mark.slow
def test_gaussian_recovers_truth(denoised_input):
    # The gaussian fit takes its covariance from a scaled scipy least-squares fit
    # (curve_fit, x_scale=jac). Its depth posterior is informative and it recovers
    # depth and duration like the samplers.
    post = _run_fit("fit_transit_gaussian", denoised_input)
    assert_posterior_schema(post)
    assert post["method"] == "gaussian"
    assert post["diagnostics"]["criterion"] == "cov_condition"
    assert post["diagnostics"]["converged"] is True

    depth_mean, duration_mean = recovered(post)
    assert_allclose(depth_mean, TRUE_DEPTH, rtol=R_DEPTH)
    assert_allclose(duration_mean, TRUE_DURATION_H, rtol=R_DUR)


@pytest.mark.slow
def test_biased_control_is_worse(denoised_input):
    # The biased fit uses a narrow prior box that excludes the true value and a
    # coarse dynesty run, so it lands away from the truth on depth and duration.
    # It is compared against the nested fit; recovery of the truth is not asserted.
    biased = _run_fit("fit_transit_biased", denoised_input)
    nested = _run_fit("fit_transit_nested", denoised_input)
    assert_posterior_schema(biased)
    assert biased["method"] == "biased"
    assert biased["diagnostics"]["criterion"] == "logz_err"

    biased_depth, biased_dur = recovered(biased)
    nested_depth, nested_dur = recovered(nested)
    assert abs(biased_depth - TRUE_DEPTH) > abs(nested_depth - TRUE_DEPTH)
    assert abs(biased_dur - TRUE_DURATION_H) > abs(nested_dur - TRUE_DURATION_H)
