"""seed, diamond_join: transform that copies the lab input value into value.json."""

import json

import daedalus.flow as dae


@dae.entry
def seed(ctx: dae.FlowContext) -> None:
    # Read the lab input and pass its value straight through.
    payload = json.loads((ctx.step_input_path / "start.json").read_text())
    value = payload["value"]

    out = {"value": value}
    (ctx.step_output_path / "value.json").write_text(json.dumps(out, indent=2))
