"""emit, flight_final_merge: emitter that writes no roster, so the engine runs one flight."""

import json

import daedalus.flow as dae


@dae.entry
def run(ctx: dae.FlowContext) -> None:
    (ctx.step_output_path / "emit.json").write_text(
        json.dumps({"step": ctx.step_id}, sort_keys=True) + "\n"
    )
