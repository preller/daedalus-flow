"""parallel / combine: walk collector; merges the four branch statistics."""

import json

import daedalus.flow as dae


@dae.entry
def combine(ctx: dae.FlowContext) -> None:
    # Keyed by the payload's "stat" field; the result is the same in any branch order.
    stats = {}
    for branch_dir in ctx.walk_inputs.values():
        payload = json.loads((branch_dir / "stat.json").read_text())
        stats[payload["stat"]] = payload["value"]

    summary = {"stats": dict(sorted(stats.items()))}
    (ctx.step_output_path / "summary.json").write_text(json.dumps(summary, indent=2))
