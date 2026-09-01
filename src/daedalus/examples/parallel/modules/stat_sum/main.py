"""parallel / stat_sum: transform; one branch, the total of the values."""

import json
import time

import daedalus.flow as dae

# A short, fixed work time. Branches use different durations so a parallel run
# clearly overlaps them and the collector visibly waits for the slowest.
WORK_SECONDS = 0.05


@dae.entry
def stat_sum(ctx: dae.FlowContext) -> None:
    values = json.loads((ctx.step_input_path / "values.json").read_text())["values"]
    # The sleep stands in for work; the overlap and the barrier show in the timings.
    time.sleep(WORK_SECONDS)
    result = {"stat": "sum", "value": sum(values)}
    (ctx.step_output_path / "stat.json").write_text(json.dumps(result, indent=2))
