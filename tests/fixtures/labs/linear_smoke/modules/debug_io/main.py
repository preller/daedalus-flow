"""debug_io, linear_smoke: transform that copies ticks.json through and records the context fields it saw."""

import json

import daedalus.flow as dae


@dae.entry
def debug_io(ctx: dae.FlowContext) -> None:
    payload = json.loads((ctx.step_input_path / "ticks.json").read_text())

    seen = {
        "step_id": ctx.step_id,
        "seed": ctx.seed,
        "flight_id": ctx.flight_id,
        "walk_id": ctx.walk_id,
    }
    out = {"ticks": payload["ticks"], "seen": seen}
    (ctx.step_output_path / "ticks.json").write_text(json.dumps(out, indent=2))
