"""coll_b, flight_final_merge: walk_collector that writes b.json, one of the three sibling outputs the flight final/ must hold."""

import json

import daedalus.flow as dae


@dae.entry
def run(ctx: dae.FlowContext) -> None:
    (ctx.step_output_path / "b.json").write_text(
        json.dumps({"from": ctx.step_id}, sort_keys=True) + "\n"
    )
