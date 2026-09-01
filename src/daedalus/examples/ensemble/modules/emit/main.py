"""ensemble / emit: emitter; one Flight per target row."""

import csv
import json

import daedalus.flow as dae


@dae.entry
def emit(ctx: dae.FlowContext) -> None:
    with (ctx.step_input_path / "targets.csv").open(newline="") as fh:
        # Skip blank lines and #-comment lines so the targets file can carry a
        # documented header (units, column meanings) without confusing the parser.
        data = [
            line for line in fh if line.strip() and not line.lstrip().startswith("#")
        ]
    rows = list(csv.DictReader(data))
    roster = [{"name": r["name"], "value": float(r["value"])} for r in rows]
    (ctx.step_output_path / "roster.json").write_text(json.dumps(roster, indent=2))
