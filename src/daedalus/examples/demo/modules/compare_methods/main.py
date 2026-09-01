"""demo / compare_methods: walk collector; distance between one target's two fits."""

import json

import numpy as np

import daedalus.flow as dae


def _hellinger_gaussian(m1: float, s1: float, m2: float, s2: float) -> float:
    # Hellinger distance between two 1D Gaussians, in closed form.
    var_sum = s1 * s1 + s2 * s2
    coef = np.sqrt(2.0 * s1 * s2 / var_sum)
    expo = np.exp(-0.25 * (m1 - m2) ** 2 / var_sum)
    return float(np.sqrt(max(1.0 - coef * expo, 0.0)))


@dae.entry
def compare_methods(ctx: dae.FlowContext) -> None:
    # Collector inputs arrive keyed by Walk in ctx.walk_inputs. Each posterior
    # names its method, so the lookup goes by that field and not by walk id.
    posteriors = {}
    for walk_dir in ctx.walk_inputs.values():
        p = json.loads((walk_dir / "posterior.json").read_text())
        posteriors[p["method"]] = p

    nested = posteriors["nested"]["depth"]
    mcmc = posteriors["mcmc"]["depth"]

    # 1D Wasserstein-1 distance on equal-size sample sets: mean absolute gap
    # between the order statistics.
    a = np.sort(np.array(nested["samples"]))
    b = np.sort(np.array(mcmc["samples"]))
    wasserstein = float(np.mean(np.abs(a - b)))
    hellinger = _hellinger_gaussian(
        nested["mean"], nested["std"], mcmc["mean"], mcmc["std"]
    )

    comparison = {
        "target": posteriors["nested"]["target"],
        "wasserstein_depth": wasserstein,
        "hellinger_depth": hellinger,
        "depth_abs_diff": abs(nested["mean"] - mcmc["mean"]),
    }
    (ctx.step_output_path / "comparison.json").write_text(
        json.dumps(comparison, indent=2)
    )
