"""parallel / stat_min: transform; one branch, the smallest value."""

import json
import time

import daedalus.flow as dae

WORK_SECONDS = 0.15


@dae.entry
def stat_min(ctx: dae.FlowContext) -> None:
    values = json.loads((ctx.step_input_path / "values.json").read_text())["values"]
    time.sleep(WORK_SECONDS)
    result = {"stat": "min", "value": min(values)}
    (ctx.step_output_path / "stat.json").write_text(json.dumps(result, indent=2))
