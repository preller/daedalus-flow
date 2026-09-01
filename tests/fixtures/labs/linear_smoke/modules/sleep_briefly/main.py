"""sleep_briefly, linear_smoke: transform that sleeps 20 ms, then copies ticks.json through."""

import json
import time

import daedalus.flow as dae


@dae.entry
def sleep_briefly(ctx: dae.FlowContext) -> None:
    time.sleep(0.02)

    payload = json.loads((ctx.step_input_path / "ticks.json").read_text())
    (ctx.step_output_path / "ticks.json").write_text(json.dumps(payload, indent=2))
