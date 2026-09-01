"""right, diamond_join: transform that adds 100 to the seed value and tags the output as right."""

import json

import daedalus.flow as dae


@dae.entry
def right(ctx: dae.FlowContext) -> None:
    # Read the seed value and add 100. For v=1 this is 101.
    payload = json.loads((ctx.step_input_path / "value.json").read_text())
    value = payload["value"] + 100

    out = {"branch": "right", "value": value}
    (ctx.step_output_path / "value.json").write_text(json.dumps(out, indent=2))
