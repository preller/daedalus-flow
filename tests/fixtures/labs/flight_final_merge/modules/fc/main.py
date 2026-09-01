"""fc, flight_final_merge: flight_collector that reads a.json, b.json and c.json from every flight final/."""

import json

import daedalus.flow as dae

EXPECTED = ("a.json", "b.json", "c.json")


@dae.entry
def run(ctx: dae.FlowContext) -> None:
    combined = {}
    for flight_id, flight_dir in sorted(ctx.flight_inputs.items()):
        combined[flight_id] = {
            name: json.loads((flight_dir / name).read_text()) for name in EXPECTED
        }
    (ctx.step_output_path / "combined.json").write_text(
        json.dumps(combined, indent=2, sort_keys=True) + "\n"
    )
