"""work, flight_one_fails: transform that echoes its flight's roster item and raises on the doomed item 20."""

import json

import daedalus.flow as dae

DOOMED_ITEM = 20


@dae.entry
def run(ctx: dae.FlowContext) -> None:
    roster = json.loads((ctx.step_input_path / "roster.json").read_text())
    flight_index = int(ctx.flight_id.split("_")[-1]) - 1
    item = roster[flight_index]
    if item == DOOMED_ITEM:
        message = f"work failed for item {DOOMED_ITEM}"
        raise RuntimeError(message)
    (ctx.step_output_path / "picked.json").write_text(
        json.dumps({"flight_id": ctx.flight_id, "item": item}, indent=2, sort_keys=True)
        + "\n"
    )
