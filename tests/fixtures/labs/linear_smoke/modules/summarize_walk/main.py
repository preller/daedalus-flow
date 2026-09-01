"""summarize_walk, linear_smoke: transform that writes the count and sum of the ticks."""

import json

import daedalus.flow as dae


@dae.entry
def summarize_walk(ctx: dae.FlowContext) -> None:
    payload = json.loads((ctx.step_input_path / "ticks.json").read_text())
    ticks = payload["ticks"]

    summary = {
        "step_id": ctx.step_id,
        "n_ticks": len(ticks),
        "sum": sum(ticks),
    }
    (ctx.step_output_path / "walk_summary.json").write_text(
        json.dumps(summary, indent=2)
    )
