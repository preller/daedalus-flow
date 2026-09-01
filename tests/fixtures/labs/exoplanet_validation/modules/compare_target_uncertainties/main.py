"""compare_target_uncertainties, exoplanet_validation: flight_collector; compares method divergence across targets and carries the plots forward."""

import json
import shutil

import numpy as np

import daedalus.flow as dae

CARRY_FILES = (
    "distances.json",
    "corner_data.json",
    "corner.png",
    "overlay_data.json",
    "overlay.png",
)
PARAMS = ("depth", "duration_h")
METRICS = ("wasserstein", "energy", "jensen_shannon", "hellinger")


def _metric_value(distances, pair, param, metric):
    # Look up one metric for one method-pair in a target's pairwise list, by pair
    # content (sorted 2-list), never by position.
    for entry in distances["pairwise"]:
        if tuple(entry["pair"]) == pair:
            return float(entry[param][metric])
    return None


def _cross_target_row(per_target_distances, targets, pair, param, metric):
    # Per-target values for one (pair, param, metric) plus their absolute diff.
    values = {}
    for target in targets:
        value = _metric_value(per_target_distances[target], pair, param, metric)
        if value is not None:
            values[target] = value
    if len(values) == len(targets) and len(values) >= 2:
        vals = list(values.values())
        abs_diff = float(np.abs(vals[0] - vals[1]))
    else:
        abs_diff = 0.0
    return {
        "pair": list(pair),
        "param": param,
        "metric": metric,
        "per_target": values,
        "abs_diff": abs_diff,
    }


@dae.entry
def compare_target_uncertainties(ctx: dae.FlowContext) -> None:
    # Key each flight by the target in its distances.json, not by the dict key.
    per_target_distances = {}
    for flight_dir in ctx.flight_inputs.values():
        distances = json.loads((flight_dir / "distances.json").read_text())
        target = distances["target"]
        per_target_distances[target] = distances

        # Copy the plots into a per-target subdir; the sink sees only this module's output.
        dest = ctx.step_output_path / target
        dest.mkdir(parents=True, exist_ok=True)
        for name in CARRY_FILES:
            shutil.copy2(flight_dir / name, dest / name)

    targets = sorted(per_target_distances)
    per_target = [
        {"target": t, "pairwise": per_target_distances[t]["pairwise"]} for t in targets
    ]

    # Deterministic union of method-pairs across all targets.
    all_pairs = sorted(
        {
            tuple(entry["pair"])
            for distances in per_target_distances.values()
            for entry in distances["pairwise"]
        }
    )

    # Flat triple-product, ordered (pair, param, metric), to avoid deep nesting.
    cross_target = [
        _cross_target_row(per_target_distances, targets, pair, param, metric)
        for pair in all_pairs
        for param in PARAMS
        for metric in METRICS
    ]

    comparison = {
        "n_targets": len(targets),
        "targets": targets,
        "per_target": per_target,
        "cross_target": cross_target,
    }
    (ctx.step_output_path / "comparison.json").write_text(
        json.dumps(comparison, indent=2)
    )
