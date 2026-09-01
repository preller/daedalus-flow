"""leaf_x (transform): one of the two branch walks created by split."""

import json

import daedalus.flow as dae


@dae.entry
def run(ctx: dae.FlowContext) -> None:
    (ctx.step_output_path / "leaf.json").write_text(
        json.dumps({"step": ctx.step_id, "walk_id": ctx.walk_id}, sort_keys=True) + "\n"
    )
