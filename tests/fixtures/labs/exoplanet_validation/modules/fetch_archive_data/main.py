"""fetch_archive_data, exoplanet_validation: transform; synthesizes one target's phase-folded transit light curve, offline and seeded."""

import json

import batman
import numpy as np

import daedalus.flow as dae

N_POINTS = 2000
T0 = 0.0
ECC = 0.0
INC_DEG = 90.0
OMEGA_DEG = 90.0
LD_U1 = 0.3
LD_U2 = 0.2
HOURS_PER_DAY = 24.0


@dae.entry
def fetch_archive_data(ctx: dae.FlowContext) -> None:
    # Flights are 1-indexed in roster order; a seeded batman model stands in for archive data.
    roster = json.loads((ctx.step_input_path / "targets.json").read_text())
    flight_index = int(ctx.flight_id.split("_")[-1]) - 1
    target = roster[flight_index]

    period_days = target["period_days"]
    rp_rstar = target["rp_rstar"]
    duration_h = target["duration_h"]
    snr = target["snr"]

    # Phase grid mapped to time in days; T0 = 0.0 is mid-transit.
    phase = np.linspace(-0.5, 0.5, N_POINTS)
    t = phase * period_days

    # Scaled semi-major axis from the central circular-transit duration formula.
    duration_days = duration_h / HOURS_PER_DAY
    a_rstar = 1.0 / np.sin(np.pi * duration_days / period_days)

    params = batman.TransitParams()
    params.t0 = T0
    params.per = period_days
    params.rp = rp_rstar
    params.a = a_rstar
    params.inc = INC_DEG
    params.ecc = ECC
    params.w = OMEGA_DEG
    params.limb_dark = "quadratic"
    params.u = [LD_U1, LD_U2]
    model = batman.TransitModel(params, t)
    flux_clean = model.light_curve(params)

    # The signal-to-noise ratio sets the per-point sigma; depth is the squared radius ratio.
    true_depth = rp_rstar**2
    sigma = true_depth / max(snr, 1.0)
    rng = np.random.default_rng(ctx.seed)
    flux = flux_clean + rng.normal(0.0, sigma, N_POINTS)

    folded = {
        "target": target["target"],
        "period_days": period_days,
        "phase": phase.tolist(),
        "flux": flux.tolist(),
        "flux_err": float(sigma),
        "true_depth": float(true_depth),
        "true_duration_h": duration_h,
        "rp_rstar": rp_rstar,
        "a_rstar": float(a_rstar),
        "snr": snr,
    }
    (ctx.step_output_path / "folded.json").write_text(json.dumps(folded, indent=2))
