"""isolation-nix / seed: brancher transform; passes the input word to both branches."""

import json

import daedalus.flow as dae


@dae.entry
def seed(ctx: dae.FlowContext) -> None:
    payload = json.loads((ctx.step_input_path / "word.json").read_text())
    (ctx.step_output_path / "word.json").write_text(json.dumps(payload, indent=2))
