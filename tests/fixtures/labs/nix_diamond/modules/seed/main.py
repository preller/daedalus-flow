"""seed - top of the diamond; passes the lab input through (stdlib only)."""

import json

import daedalus.flow as dae


@dae.entry
def seed(ctx: dae.FlowContext) -> None:
    payload = json.loads((ctx.step_input_path / "start.json").read_text())
    (ctx.step_output_path / "value.json").write_text(json.dumps(payload, indent=2))
