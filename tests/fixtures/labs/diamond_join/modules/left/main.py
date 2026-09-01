"""left, diamond_join: transform that adds 10 to the seed value and tags the output as left."""

import json

import daedalus.flow as dae


@dae.entry
def left(ctx: dae.FlowContext) -> None:
    # Read the seed value and add 10. For v=1 this is 11.
    payload = json.loads((ctx.step_input_path / "value.json").read_text())
    value = payload["value"] + 10

    out = {"branch": "left", "value": value}
    (ctx.step_output_path / "value.json").write_text(json.dumps(out, indent=2))
