"""demo / summarize_population: flight collector; mean disagreement across targets."""

import json

import numpy as np

import daedalus.flow as dae


@dae.entry
def summarize_population(ctx: dae.FlowContext) -> None:
    # Flight outputs arrive keyed by Flight in ctx.flight_inputs. The per-target
    # list is sorted by name, which keeps the summary the same in any Flight order.
    comparisons = [
        json.loads((flight_dir / "comparison.json").read_text())
        for flight_dir in ctx.flight_inputs.values()
    ]
    wasserstein = np.array([c["wasserstein_depth"] for c in comparisons])
    hellinger = np.array([c["hellinger_depth"] for c in comparisons])

    summary = {
        "n_targets": len(comparisons),
        "mean_wasserstein_depth": float(np.mean(wasserstein)),
        "mean_hellinger_depth": float(np.mean(hellinger)),
        "per_target": sorted(comparisons, key=lambda c: c["target"]),
    }
    (ctx.step_output_path / "summary.json").write_text(json.dumps(summary, indent=2))
