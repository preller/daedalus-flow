"""denoise_lightcurve, exoplanet_validation: transform; bins the folded light curve with lightkurve, and the four fits branch from it."""

import json

import lightkurve as lk
import numpy as np

import daedalus.flow as dae

POINTS_PER_BIN = 5


@dae.entry
def denoise_lightcurve(ctx: dae.FlowContext) -> None:
    # Binning cuts white noise by sqrt(points per bin) and keeps the transit depth.
    folded = json.loads((ctx.step_input_path / "folded.json").read_text())

    phase = np.asarray(folded["phase"], dtype=float)
    flux = np.asarray(folded["flux"], dtype=float)
    flux_err = float(folded["flux_err"])

    n_bins = max(1, phase.size // POINTS_PER_BIN)
    curve = lk.LightCurve(time=phase, flux=flux)
    binned = curve.bin(bins=n_bins)

    keep = np.isfinite(np.asarray(binned.flux.value, dtype=float))
    phase_binned = np.asarray(binned.time.value, dtype=float)[keep]
    flux_binned = np.asarray(binned.flux.value, dtype=float)[keep]

    # Uncertainty of each binned point is the standard error of the mean: the
    # per-point sigma reduced by sqrt(points-per-bin).
    err_binned = flux_err / float(np.sqrt(POINTS_PER_BIN))

    denoised = {
        "target": folded["target"],
        "period_days": float(folded["period_days"]),
        "phase": phase_binned.tolist(),
        "flux_denoised": flux_binned.tolist(),
        "flux_err": float(np.median(err_binned)),
        "true_depth": float(folded["true_depth"]),
        "true_duration_h": float(folded["true_duration_h"]),
        "rp_rstar": float(folded["rp_rstar"]),
        "a_rstar": float(folded["a_rstar"]),
        "snr": float(folded["snr"]),
    }
    (ctx.step_output_path / "denoised.json").write_text(json.dumps(denoised, indent=2))
