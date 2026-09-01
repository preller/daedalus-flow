"""demo / emit_targets: emitter; one Flight per target row."""

import csv
import json

import daedalus.flow as dae


@dae.entry
def emit_targets(ctx: dae.FlowContext) -> None:
    # One roster entry per row. daedalus starts one Flight per entry, in order,
    # and downstream steps pick out their row with ctx.flight_id.
    with (ctx.step_input_path / "targets.csv").open(newline="") as fh:
        rows = list(csv.DictReader(fh))

    roster = [
        {
            "target": r["target"],
            "period_days": float(r["period_days"]),
            "rp_rstar": float(r["rp_rstar"]),
            "duration_h": float(r["duration_h"]),
            "snr": float(r["snr"]),
        }
        for r in rows
    ]
    (ctx.step_output_path / "targets.json").write_text(json.dumps(roster, indent=2))
