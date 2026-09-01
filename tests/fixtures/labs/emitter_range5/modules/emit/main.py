"""emit, emitter_range5: emitter that writes input/items.json back as the flight roster, so M is its length."""

import json

import daedalus.flow as dae


@dae.entry
def run(ctx: dae.FlowContext) -> None:
    items = json.loads((ctx.step_input_path / "items.json").read_text())
    (ctx.step_output_path / "roster.json").write_text(
        json.dumps(items, indent=2, sort_keys=True) + "\n"
    )
