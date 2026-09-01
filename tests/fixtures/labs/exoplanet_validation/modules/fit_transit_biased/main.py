"""fit_transit_biased, exoplanet_validation: transform; dynesty fit under a narrow prior that excludes the truth, the negative control."""

import json

import batman
import dynesty
import numpy as np
from dynesty.utils import resample_equal

import daedalus.flow as dae

T0 = 0.0
ECC = 0.0
INC_DEG = 90.0
OMEGA_DEG = 90.0
LD_U1 = 0.3
LD_U2 = 0.2
HOURS_PER_DAY = 24.0
N_LIVE = 50
DLOGZ = 5.0
N_SAMPLES = 2000
BOUND = "multi"
N_DIM = 2
LOGZ_ERR_MAX = 1.0
BIAS_FACTOR = 1.5
PRIOR_WIDTH = 0.25


def _model_flux(depth, duration_h, phase, period_days):
    # Build a batman transit model from (depth, duration_h), holding all other
    # geometry fixed at the module constants. rp = sqrt(depth); a/Rstar is
    # recovered from the duration via the central-transit duration formula.
    rp = np.sqrt(max(depth, 0.0))
    duration_days = duration_h / HOURS_PER_DAY
    a_rstar = 1.0 / np.sin(np.pi * duration_days / period_days)
    params = batman.TransitParams()
    params.t0 = T0
    params.per = period_days
    params.rp = rp
    params.a = a_rstar
    params.inc = INC_DEG
    params.ecc = ECC
    params.w = OMEGA_DEG
    params.limb_dark = "quadratic"
    params.u = [LD_U1, LD_U2]
    t = phase * period_days
    model = batman.TransitModel(params, t)
    return model.light_curve(params)


def _log_likelihood(theta, phase, flux, flux_err, period_days):
    # Gaussian log-likelihood of the denoised flux given (depth, duration_h).
    depth, duration_h = theta
    if depth <= 0.0 or duration_h <= 0.0:
        return -np.inf
    model = _model_flux(depth, duration_h, phase, period_days)
    return -0.5 * np.sum(((flux - model) / flux_err) ** 2)


@dae.entry
def fit_transit_biased(ctx: dae.FlowContext) -> None:
    # A coarse dynesty run, 50 live points and a loose stop, under a shifted prior.
    denoised = json.loads((ctx.step_input_path / "denoised.json").read_text())
    phase = np.array(denoised["phase"])
    flux = np.array(denoised["flux_denoised"])
    flux_err = float(denoised["flux_err"])
    period_days = float(denoised["period_days"])
    a_rstar = float(denoised["a_rstar"])
    true_depth = float(denoised["true_depth"])
    true_duration_h = float(denoised["true_duration_h"])

    rng = np.random.default_rng(ctx.seed)

    # The prior box sits 1.5x above the truth and is narrow enough to exclude it,
    # so the posterior lands away from the truth whatever the data says.
    depth_center = true_depth * BIAS_FACTOR
    duration_center = true_duration_h * BIAS_FACTOR
    depth_lo = depth_center * (1.0 - PRIOR_WIDTH)
    depth_hi = depth_center * (1.0 + PRIOR_WIDTH)
    dur_lo = duration_center * (1.0 - PRIOR_WIDTH)
    dur_hi = duration_center * (1.0 + PRIOR_WIDTH)

    def prior_transform(u):
        depth = depth_lo + u[0] * (depth_hi - depth_lo)
        duration_h = dur_lo + u[1] * (dur_hi - dur_lo)
        return np.array([depth, duration_h])

    def loglike(theta):
        return _log_likelihood(theta, phase, flux, flux_err, period_days)

    sampler = dynesty.DynamicNestedSampler(
        loglike,
        prior_transform,
        ndim=N_DIM,
        nlive=N_LIVE,
        bound=BOUND,
        rstate=rng,
    )
    sampler.run_nested(dlogz_init=DLOGZ, print_progress=False)
    results = sampler.results

    logz_err = float(results.logzerr[-1])
    converged = bool(logz_err < LOGZ_ERR_MAX)

    weights = np.exp(results.logwt - results.logz[-1])
    eq = resample_equal(results.samples, weights, rstate=rng)

    total = eq.shape[0]
    if total > N_SAMPLES:
        idx = rng.choice(total, N_SAMPLES, replace=False)
        eq = eq[idx]
    depth_samples = eq[:, 0]
    duration_samples = eq[:, 1]

    posterior = {
        "method": "biased",
        "target": denoised["target"],
        "depth": {
            "mean": float(np.mean(depth_samples)),
            "std": float(np.std(depth_samples)),
            "samples": np.asarray(depth_samples).tolist(),
        },
        "duration_h": {
            "mean": float(np.mean(duration_samples)),
            "std": float(np.std(duration_samples)),
            "samples": np.asarray(duration_samples).tolist(),
        },
        "diagnostics": {
            "criterion": "logz_err",
            "value": logz_err,
            "converged": converged,
        },
        "period_days": period_days,
        "a_rstar": a_rstar,
        "observed": {
            "phase": np.asarray(phase).tolist(),
            "flux_denoised": np.asarray(flux).tolist(),
            "flux_err": flux_err,
        },
    }
    (ctx.step_output_path / "posterior.json").write_text(
        json.dumps(posterior, indent=2)
    )
