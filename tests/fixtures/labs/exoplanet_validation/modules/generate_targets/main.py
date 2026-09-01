"""generate_targets, exoplanet_validation: emitter; one flight per row of targets.csv."""

import csv
import json

import daedalus.flow as dae


@dae.entry
def generate_targets(ctx: dae.FlowContext) -> None:
    # One roster entry per row, in file order; downstream steps index it by ctx.flight_id.
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
