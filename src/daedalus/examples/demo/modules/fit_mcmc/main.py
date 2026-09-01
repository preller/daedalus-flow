"""demo / fit_mcmc: transform; the mcmc Walk, a stand-in for an emcee fit."""

import json

import numpy as np

import daedalus.flow as dae

N_SAMPLES = 2000
# Widens the depth error past fit_nested's analytic estimate.
ERR_WIDENING = 1.15


@dae.entry
def fit_mcmc(ctx: dae.FlowContext) -> None:
    # Same folded curve as fit_nested, but a mean-based depth and a wider error
    # stand in for MCMC. The small gap from fit_nested is what compare_methods
    # measures.
    folded = json.loads((ctx.step_input_path / "folded.json").read_text())
    phase = np.array(folded["phase"])
    flux = np.array(folded["flux"])
    err = float(folded["flux_err"])
    half_width = float(folded["half_width"])

    in_transit = np.abs(phase) <= half_width
    depth_hat = float(np.mean(flux[~in_transit]) - np.mean(flux[in_transit]))
    depth_err = ERR_WIDENING * err / np.sqrt(max(int(in_transit.sum()), 1))

    rng = np.random.default_rng(ctx.seed + 1)
    samples = rng.normal(depth_hat, depth_err, N_SAMPLES)

    posterior = {
        "method": "mcmc",
        "target": folded["target"],
        "depth": {
            "mean": float(np.mean(samples)),
            "std": float(np.std(samples)),
            "samples": samples.tolist(),
        },
    }
    (ctx.step_output_path / "posterior.json").write_text(
        json.dumps(posterior, indent=2)
    )
