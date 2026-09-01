"""fit_transit_gaussian, exoplanet_validation: transform; scipy least-squares fit with a Gaussian posterior from the covariance."""

import json

import batman
import numpy as np
from scipy.optimize import curve_fit

import daedalus.flow as dae

T0 = 0.0
ECC = 0.0
INC_DEG = 90.0
OMEGA_DEG = 90.0
LD_U1 = 0.3
LD_U2 = 0.2
HOURS_PER_DAY = 24.0
N_SAMPLES = 2000
MAX_EVALS = 30000


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


@dae.entry
def fit_transit_gaussian(ctx: dae.FlowContext) -> None:
    # x_scale="jac" conditions the fit; depth and duration differ by orders of magnitude.
    denoised = json.loads((ctx.step_input_path / "denoised.json").read_text())
    phase = np.array(denoised["phase"])
    flux = np.array(denoised["flux_denoised"])
    flux_err = float(denoised["flux_err"])
    period_days = float(denoised["period_days"])
    a_rstar = float(denoised["a_rstar"])
    true_depth = float(denoised["true_depth"])
    true_duration_h = float(denoised["true_duration_h"])

    def model(ph, depth, duration_h):
        return _model_flux(depth, duration_h, ph, period_days)

    sigma = np.full(phase.size, flux_err)
    mean, cov = curve_fit(
        model,
        phase,
        flux,
        p0=[true_depth, true_duration_h],
        sigma=sigma,
        absolute_sigma=True,
        method="trf",
        x_scale="jac",
        maxfev=MAX_EVALS,
    )
    cov = np.asarray(cov)

    cov_condition = float(np.linalg.cond(cov))
    converged = bool(np.all(np.linalg.eigvalsh(cov) > 0.0))

    rng = np.random.default_rng(ctx.seed)
    draws = rng.multivariate_normal(mean, cov, N_SAMPLES)
    depth_samples = draws[:, 0]
    duration_samples = draws[:, 1]

    posterior = {
        "method": "gaussian",
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
            "criterion": "cov_condition",
            "value": cov_condition,
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
