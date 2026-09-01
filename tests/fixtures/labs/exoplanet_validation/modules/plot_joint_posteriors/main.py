"""plot_joint_posteriors, exoplanet_validation: walk_collector; corner plot of the four methods' posteriors for one flight."""

import json

import matplotlib
import numpy as np

matplotlib.use("Agg")
import corner
import matplotlib.pyplot as plt

import daedalus.flow as dae

PARAMS = ["depth", "duration_h"]
CORNER_COLORS = {
    "biased": "tab:red",
    "gaussian": "tab:green",
    "mcmc": "tab:blue",
    "nested": "tab:purple",
}


@dae.entry
def plot_joint_posteriors(ctx: dae.FlowContext) -> None:
    # Key each posterior by its own method field, not by walk id.
    posteriors = {}
    for walk_dir in ctx.walk_inputs.values():
        p = json.loads((walk_dir / "posterior.json").read_text())
        posteriors[p["method"]] = p

    methods = sorted(posteriors)
    target = posteriors[methods[0]]["target"]

    # The summary statistics are the goldened artifact; the png is not.
    per_method = {}
    for method in methods:
        p = posteriors[method]
        per_method[method] = {
            "depth_mean": float(p["depth"]["mean"]),
            "depth_std": float(p["depth"]["std"]),
            "duration_h_mean": float(p["duration_h"]["mean"]),
            "duration_h_std": float(p["duration_h"]["std"]),
        }

    corner_data = {
        "target": target,
        "params": PARAMS,
        "methods": methods,
        "per_method": per_method,
    }
    (ctx.step_output_path / "corner_data.json").write_text(
        json.dumps(corner_data, indent=2)
    )

    # Overlay every method's joint (depth, duration_h) posterior on one figure.
    # The first method seeds the figure; the rest reuse it via fig=fig.
    fig = None
    for method in methods:
        p = posteriors[method]
        data = np.column_stack(
            [np.asarray(p["depth"]["samples"]), np.asarray(p["duration_h"]["samples"])]
        )
        fig = corner.corner(
            data,
            fig=fig,
            labels=PARAMS,
            color=CORNER_COLORS.get(method, "black"),
            hist_kwargs={"density": True},
            plot_datapoints=False,
        )
    fig.suptitle(f"{target}: joint depth-duration posteriors")
    fig.savefig(ctx.step_output_path / "corner.png")
    plt.close(fig)
