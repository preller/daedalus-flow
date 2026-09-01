"""parallel / split: brancher transform; hands the values to all four branches."""

import json

import daedalus.flow as dae


@dae.entry
def split(ctx: dae.FlowContext) -> None:
    payload = json.loads((ctx.step_input_path / "dataset.json").read_text())
    values = [float(v) for v in payload["values"]]
    (ctx.step_output_path / "values.json").write_text(
        json.dumps({"values": values}, indent=2)
    )
