"""work, emitter_range5: transform that picks its flight's roster row (1-indexed flight_id) and echoes it."""

import json

import daedalus.flow as dae


@dae.entry
def run(ctx: dae.FlowContext) -> None:
    roster = json.loads((ctx.step_input_path / "roster.json").read_text())
    flight_index = int(ctx.flight_id.split("_")[-1]) - 1
    item = roster[flight_index]
    (ctx.step_output_path / "picked.json").write_text(
        json.dumps({"flight_id": ctx.flight_id, "item": item}, indent=2, sort_keys=True)
        + "\n"
    )
