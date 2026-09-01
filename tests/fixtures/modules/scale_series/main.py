"""scale_series: transform fixture; multiplies the input values by 3 with numpy; see tests/fixtures/README.md."""

import json

import numpy as np

import daedalus.flow as dae


@dae.entry
def scale_series(ctx: dae.FlowContext) -> None:
    # Read the series, multiply every value by the integer factor with numpy,
    # then convert back to a plain list of python ints for json.
    series = json.loads((ctx.step_input_path / "series.json").read_text())

    factor = 3
    scaled = np.array(series["values"]) * factor
    values = [int(v) for v in scaled.tolist()]

    out = {"factor": factor, "values": values}
    (ctx.step_output_path / "scaled.json").write_text(json.dumps(out, indent=2))
