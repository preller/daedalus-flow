"""parallel / stat_max: transform; one branch, the largest value."""

import json
import time

import daedalus.flow as dae

WORK_SECONDS = 0.10


@dae.entry
def stat_max(ctx: dae.FlowContext) -> None:
    values = json.loads((ctx.step_input_path / "values.json").read_text())["values"]
    time.sleep(WORK_SECONDS)
    result = {"stat": "max", "value": max(values)}
    (ctx.step_output_path / "stat.json").write_text(json.dumps(result, indent=2))
