"""ensemble / analyze: transform; a deterministic score for one target per Flight."""

import json

import daedalus.flow as dae


@dae.entry
def analyze(ctx: dae.FlowContext) -> None:
    roster = json.loads((ctx.step_input_path / "roster.json").read_text())
    # Flights are 1-indexed in roster order.
    flight_index = int(ctx.flight_id.split("_")[-1]) - 1
    target = roster[flight_index]
    result = {
        "name": target["name"],
        "value": target["value"],
        "score": target["value"] ** 2,
    }
    (ctx.step_output_path / "result.json").write_text(json.dumps(result, indent=2))
