"""demo / fetch_data: transform; a synthetic phase-folded light curve per target."""

import json

import numpy as np

import daedalus.flow as dae


@dae.entry
def fetch_data(ctx: dae.FlowContext) -> None:
    # Flights are 1-indexed in roster order. The curve is synthetic (numpy only)
    # so the demo runs anywhere; a real lab would fetch it with lightkurve.
    # Noise scales with the target's signal to noise; the seed fixes the draw.
    roster = json.loads((ctx.step_input_path / "targets.json").read_text())
    flight_index = int(ctx.flight_id.split("_")[-1]) - 1
    target = roster[flight_index]

    rng = np.random.default_rng(ctx.seed)
    n_points = 400
    phase = np.linspace(-0.5, 0.5, n_points)

    depth = target["rp_rstar"] ** 2
    half_width = (target["duration_h"] / 24.0) / target["period_days"] / 2.0
    in_transit = np.abs(phase) <= half_width

    flux = np.ones(n_points)
    flux[in_transit] -= depth
    noise = depth / max(target["snr"], 1.0)
    flux = flux + rng.normal(0.0, noise, n_points)

    folded = {
        "target": target["target"],
        "period_days": target["period_days"],
        "phase": phase.tolist(),
        "flux": flux.tolist(),
        "flux_err": noise,
        "half_width": half_width,
        "true_depth": depth,
    }
    (ctx.step_output_path / "folded.json").write_text(json.dumps(folded, indent=2))
