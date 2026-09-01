"""split, flight_final_merge_m2: transform with two transform successors, so each flight carries two walks."""

import json

import daedalus.flow as dae


@dae.entry
def run(ctx: dae.FlowContext) -> None:
    (ctx.step_output_path / "split.json").write_text(
        json.dumps({"step": ctx.step_id}, sort_keys=True) + "\n"
    )
