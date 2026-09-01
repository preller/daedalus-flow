"""fit_transit_mcmc, exoplanet_validation: transform; emcee fit of the batman transit model with an R-hat convergence check."""

import json

import batman
import emcee
import numpy as np

import daedalus.flow as dae

T0 = 0.0
ECC = 0.0
INC_DEG = 90.0
OMEGA_DEG = 90.0
LD_U1 = 0.3
LD_U2 = 0.2
HOURS_PER_DAY = 24.0
N_WALKERS = 64
N_STEPS = 5000
N_BURN = 1000
N_DIM = 2
N_SAMPLES = 2000
# Gelman-Rubin threshold (Gelman and Rubin 1992).
RHAT_MAX = 1.1
BALL_DEPTH_SCALE = 0.01
BALL_DURATION_SCALE = 0.01
PRIOR_DEPTH_WIDTH = 0.5
PRIOR_DURATION_WIDTH = 0.5


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


def _rhat(chain):
    # Gelman-Rubin R-hat per parameter from a (steps, walkers, dim) chain:
    # the ratio of the marginal posterior variance to the within-walker
    # variance, split-chain across walkers.
    n_steps = chain.shape[0]
    means = chain.mean(axis=0)
    within = chain.var(axis=0, ddof=1).mean(axis=0)
    between = n_steps * means.var(axis=0, ddof=1)
    var_hat = (n_steps - 1) / n_steps * within + between / n_steps
    return np.sqrt(var_hat / within)


@dae.entry
def fit_transit_mcmc(ctx: dae.FlowContext) -> None:
    denoised = json.loads((ctx.step_input_path / "denoised.json").read_text())
    phase = np.array(denoised["phase"])
    flux = np.array(denoised["flux_denoised"])
    flux_err = float(denoised["flux_err"])
    period_days = float(denoised["period_days"])
    a_rstar = float(denoised["a_rstar"])
    true_depth = float(denoised["true_depth"])
    true_duration_h = float(denoised["true_duration_h"])

    # emcee's State.random_state accepts only a RandomState state tuple; a
    # Generator falls back to the global unseeded stream. Use one seeded RandomState.
    rng = np.random.RandomState(ctx.seed)

    depth_lo = true_depth * (1.0 - PRIOR_DEPTH_WIDTH)
    depth_hi = true_depth * (1.0 + PRIOR_DEPTH_WIDTH)
    dur_lo = true_duration_h * (1.0 - PRIOR_DURATION_WIDTH)
    dur_hi = true_duration_h * (1.0 + PRIOR_DURATION_WIDTH)

    def log_prob(theta):
        depth, duration_h = theta
        if not (depth_lo <= depth <= depth_hi):
            return -np.inf
        if not (dur_lo <= duration_h <= dur_hi):
            return -np.inf
        return _log_likelihood(theta, phase, flux, flux_err, period_days)

    def initial_ball(generator):
        center = np.array([true_depth, true_duration_h])
        scale = np.array(
            [true_depth * BALL_DEPTH_SCALE, true_duration_h * BALL_DURATION_SCALE]
        )
        return center + scale * generator.normal(0.0, 1.0, (N_WALKERS, N_DIM))

    p0 = initial_ball(rng)
    sampler = emcee.EnsembleSampler(N_WALKERS, N_DIM, log_prob)
    # get_state(), not the RandomState itself: set_state expects the tuple.
    initial_state = emcee.State(p0, random_state=rng.get_state())
    sampler.run_mcmc(initial_state, N_STEPS, progress=False)

    chain = sampler.get_chain(discard=N_BURN, flat=False)
    flat = sampler.get_chain(discard=N_BURN, flat=True)

    rhat = _rhat(chain)
    rhat_max = float(np.max(rhat))
    converged = bool(rhat_max < RHAT_MAX)

    total = flat.shape[0]
    if total > N_SAMPLES:
        idx = rng.choice(total, N_SAMPLES, replace=False)
        flat = flat[idx]
    depth_samples = flat[:, 0]
    duration_samples = flat[:, 1]

    posterior = {
        "method": "mcmc",
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
            "criterion": "rhat_max",
            "value": rhat_max,
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
