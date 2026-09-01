"""plot_method_overlay, exoplanet_validation: walk_collector; overlays the four fitted models on the data with residuals."""

import json

import batman
import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

import daedalus.flow as dae

T0 = 0.0
ECC = 0.0
INC_DEG = 90.0
OMEGA_DEG = 90.0
LD_U1 = 0.3
LD_U2 = 0.2
HOURS_PER_DAY = 24.0
N_DIM = 2


def _model_flux(phase, period_days, depth, duration_h):
    """Rebuild a batman transit model from a fitted (depth, duration_h) pair."""
    rp = np.sqrt(max(depth, 0.0))
    duration_days = duration_h / HOURS_PER_DAY
    a_rstar = 1.0 / np.sin(np.pi * duration_days / period_days)
    t = phase * period_days
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
    model = batman.TransitModel(params, t)
    return model.light_curve(params)


@dae.entry
def plot_method_overlay(ctx: dae.FlowContext) -> None:
    posteriors = {}
    for walk_dir in ctx.walk_inputs.values():
        p = json.loads((walk_dir / "posterior.json").read_text())
        posteriors[p["method"]] = p

    methods = sorted(posteriors)
    any_post = posteriors[methods[0]]
    target = any_post["target"]

    observed = any_post["observed"]
    phase = np.asarray(observed["phase"], dtype=float)
    obs_flux = np.asarray(observed["flux_denoised"], dtype=float)
    flux_err = float(observed["flux_err"])
    n_points = phase.size

    per_method = {}
    model_curves = {}
    for method in methods:
        post = posteriors[method]
        period_days = float(post["period_days"])
        depth_mean = float(post["depth"]["mean"])
        duration_mean = float(post["duration_h"]["mean"])
        model_flux = _model_flux(phase, period_days, depth_mean, duration_mean)
        model_curves[method] = model_flux

        resid = obs_flux - model_flux
        rms = np.sqrt(np.mean(resid**2))
        chi2 = np.sum((resid / flux_err) ** 2)
        reduced_chi2 = chi2 / (n_points - N_DIM)
        per_method[method] = {
            "rms": float(rms),
            "reduced_chi2": float(reduced_chi2),
        }

    overlay_data = {
        "target": target,
        "methods": methods,
        "per_method": per_method,
    }
    (ctx.step_output_path / "overlay_data.json").write_text(
        json.dumps(overlay_data, indent=2)
    )

    fig, (ax_top, ax_bot) = plt.subplots(2, 1, sharex=True)
    ax_top.scatter(phase, obs_flux, s=4, color="0.6", label="observed")
    for method in methods:
        model_flux = model_curves[method]
        ax_top.plot(phase, model_flux, label=method)
        ax_bot.plot(phase, obs_flux - model_flux, label=method)
    ax_top.set_ylabel("normalized flux")
    ax_top.set_title(f"{target} method overlay")
    ax_top.legend(loc="lower right")
    ax_bot.set_xlabel("orbital phase")
    ax_bot.set_ylabel("residual")
    ax_bot.axhline(0.0, color="0.6", linewidth=0.8)
    fig.savefig(ctx.step_output_path / "overlay.png")
    plt.close(fig)
