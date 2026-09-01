"""demo / fit_nested: transform; the nested Walk, a stand-in for a dynesty fit."""

import json

import numpy as np

import daedalus.flow as dae

N_SAMPLES = 2000


@dae.entry
def fit_nested(ctx: dae.FlowContext) -> None:
    # Depth is the contrast between out-of-transit and in-transit flux; a
    # median-based estimator stands in for nested sampling. The seed fixes the
    # posterior draw.
    folded = json.loads((ctx.step_input_path / "folded.json").read_text())
    phase = np.array(folded["phase"])
    flux = np.array(folded["flux"])
    err = float(folded["flux_err"])
    half_width = float(folded["half_width"])

    in_transit = np.abs(phase) <= half_width
    depth_hat = float(np.median(flux[~in_transit]) - np.median(flux[in_transit]))
    depth_err = err / np.sqrt(max(int(in_transit.sum()), 1))

    rng = np.random.default_rng(ctx.seed)
    samples = rng.normal(depth_hat, depth_err, N_SAMPLES)

    posterior = {
        "method": "nested",
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
