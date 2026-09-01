"""coll_b, flight_final_merge_m2: walk_collector that writes b.json tagged with its own flight_id."""

import json

import daedalus.flow as dae


@dae.entry
def run(ctx: dae.FlowContext) -> None:
    (ctx.step_output_path / "b.json").write_text(
        json.dumps({"from": ctx.step_id, "flight": ctx.flight_id}, sort_keys=True)
        + "\n"
    )
