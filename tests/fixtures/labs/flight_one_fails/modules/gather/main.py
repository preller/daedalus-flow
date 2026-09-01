"""gather, flight_one_fails: flight_collector that keeps the lab well formed; it never runs once work fails."""

import json

import daedalus.flow as dae


@dae.entry
def run(ctx: dae.FlowContext) -> None:
    items = [
        json.loads((d / "picked.json").read_text())["item"]
        for d in ctx.flight_inputs.values()
    ]
    gathered = sorted(items, key=lambda x: json.dumps(x, sort_keys=True))
    (ctx.step_output_path / "gathered.json").write_text(
        json.dumps(gathered, indent=2) + "\n"
    )
