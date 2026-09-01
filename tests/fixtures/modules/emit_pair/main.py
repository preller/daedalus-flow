"""emit_pair: emitter fixture; one roster entry per row of seed.csv; see tests/fixtures/README.md."""

import csv
import json

import daedalus.flow as dae


@dae.entry
def emit_pair(ctx: dae.FlowContext) -> None:
    # Read the seed table and write the Flight roster: one entry per row.
    # daedalus starts one Flight per roster entry. value is parsed to int.
    with (ctx.step_input_path / "seed.csv").open(newline="") as fh:
        rows = list(csv.DictReader(fh))

    roster = [{"target": r["target"], "value": int(r["value"])} for r in rows]
    (ctx.step_output_path / "roster.json").write_text(json.dumps(roster, indent=2))
