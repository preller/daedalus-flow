"""coll_c, flight_final_merge: walk_collector that writes c.json, one of the three sibling outputs the flight final/ must hold."""

import json

import daedalus.flow as dae


@dae.entry
def run(ctx: dae.FlowContext) -> None:
    (ctx.step_output_path / "c.json").write_text(
        json.dumps({"from": ctx.step_id}, sort_keys=True) + "\n"
    )
