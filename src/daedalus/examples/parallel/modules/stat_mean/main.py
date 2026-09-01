"""parallel / stat_mean: transform; one branch, the mean value."""

import json
import statistics
import time

import daedalus.flow as dae

WORK_SECONDS = 0.20  # the longest branch, so combine visibly waits for it


@dae.entry
def stat_mean(ctx: dae.FlowContext) -> None:
    values = json.loads((ctx.step_input_path / "values.json").read_text())["values"]
    time.sleep(WORK_SECONDS)
    result = {"stat": "mean", "value": statistics.fmean(values)}
    (ctx.step_output_path / "stat.json").write_text(json.dumps(result, indent=2))
