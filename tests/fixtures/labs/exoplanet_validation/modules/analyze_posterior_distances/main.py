"""analyze_posterior_distances, exoplanet_validation: walk_collector; pairwise distances between the four posteriors of a flight."""

import itertools
import json

import numpy as np
from scipy.spatial.distance import jensenshannon
from scipy.stats import energy_distance, wasserstein_distance

import daedalus.flow as dae

N_BINS = 50
EPS = 1e-12
PARAMS = ("depth", "duration_h")


def _hellinger_gaussian(m1: float, s1: float, m2: float, s2: float) -> float:
    # Hellinger distance between two 1D Gaussians, in closed form.
    var_sum = s1 * s1 + s2 * s2
    coef = np.sqrt(2.0 * s1 * s2 / var_sum)
    expo = np.exp(-0.25 * (m1 - m2) ** 2 / var_sum)
    return float(np.sqrt(max(1.0 - coef * expo, 0.0)))


def _jensen_shannon(a: np.ndarray, b: np.ndarray) -> float:
    # Histogram both sample sets on a shared bin edge set, normalize to
    # probability vectors with a tiny floor, then take the Jensen-Shannon distance.
    bins = np.histogram_bin_edges(np.concatenate([a, b]), bins=N_BINS)
    p, _ = np.histogram(a, bins=bins, density=False)
    q, _ = np.histogram(b, bins=bins, density=False)
    p = p.astype(float) + EPS
    q = q.astype(float) + EPS
    p = p / p.sum()
    q = q / q.sum()
    return float(jensenshannon(p, q))


def _param_distances(pa: dict, pb: dict) -> dict:
    # All four metrics between two methods for a single parameter marginal.
    a = np.asarray(pa["samples"], dtype=float)
    b = np.asarray(pb["samples"], dtype=float)
    return {
        "wasserstein": float(wasserstein_distance(a, b)),
        "energy": float(energy_distance(a, b)),
        "jensen_shannon": _jensen_shannon(a, b),
        "hellinger": _hellinger_gaussian(pa["mean"], pa["std"], pb["mean"], pb["std"]),
    }


@dae.entry
def analyze_posterior_distances(ctx: dae.FlowContext) -> None:
    # Key each posterior by its own method field, not by walk id, then write the
    # pairwise distances across the four methods for both fitted parameters.
    posteriors = {}
    for walk_dir in ctx.walk_inputs.values():
        p = json.loads((walk_dir / "posterior.json").read_text())
        posteriors[p["method"]] = p

    methods = sorted(posteriors)
    pairwise = []
    for m_a, m_b in itertools.combinations(methods, 2):
        entry: dict = {"pair": [m_a, m_b]}
        for param in PARAMS:
            entry[param] = _param_distances(
                posteriors[m_a][param], posteriors[m_b][param]
            )
        pairwise.append(entry)

    distances = {
        "target": posteriors[methods[0]]["target"],
        "methods": methods,
        "pairwise": pairwise,
    }
    (ctx.step_output_path / "distances.json").write_text(
        json.dumps(distances, indent=2)
    )
