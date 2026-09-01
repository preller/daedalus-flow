"""emit, flight_final_merge_m2: emitter that writes a two-item roster.json, so the engine fans out to two flights."""

import json

import daedalus.flow as dae


@dae.entry
def run(ctx: dae.FlowContext) -> None:
    roster = [{"flight": 1}, {"flight": 2}]
    (ctx.step_output_path / "roster.json").write_text(
        json.dumps(roster, indent=2, sort_keys=True) + "\n"
    )
