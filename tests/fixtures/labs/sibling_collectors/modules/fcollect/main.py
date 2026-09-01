"""fcollect, sibling_collectors: pass-through shape fixture (flight_collector); see tests/fixtures/README.md."""

import json

import daedalus.flow as dae


@dae.entry
def run(ctx: dae.FlowContext) -> None:
    marker = {"seed": ctx.seed, "step_id": ctx.step_id, "walk_id": ctx.walk_id}
    (ctx.step_output_path / "marker.json").write_text(
        json.dumps(marker, indent=2, sort_keys=True) + "\n"
    )
