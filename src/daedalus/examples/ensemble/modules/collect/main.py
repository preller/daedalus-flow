"""ensemble / collect: flight collector; one summary over every Flight."""

import json
import statistics

import daedalus.flow as dae


@dae.entry
def collect(ctx: dae.FlowContext) -> None:
    results = [
        json.loads((flight_dir / "result.json").read_text())
        for flight_dir in ctx.flight_inputs.values()
    ]
    # Sorted by name; the summary is the same in any Flight order.
    summary = {
        "n_targets": len(results),
        "mean_score": statistics.fmean(r["score"] for r in results) if results else 0.0,
        "per_target": sorted(results, key=lambda r: r["name"]),
    }
    (ctx.step_output_path / "summary.json").write_text(json.dumps(summary, indent=2))
