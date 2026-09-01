"""sink (transform): the lone flow sink; files the flight_collector result."""

import json

import daedalus.flow as dae


@dae.entry
def run(ctx: dae.FlowContext) -> None:
    (ctx.step_output_path / "done.json").write_text(
        json.dumps({"step": ctx.step_id}, sort_keys=True) + "\n"
    )
