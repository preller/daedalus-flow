"""minimal / normalize: transform; divides a raw light curve's flux by its median."""

import csv
import json
import statistics

import daedalus.flow as dae


@dae.entry
def normalize(ctx: dae.FlowContext) -> None:
    # Divide the flux by its median so the out-of-transit baseline sits at 1.0.
    # The minimal example is the on-ramp and stays stdlib-only, so
    # statistics.median stands in for numpy.
    with (ctx.step_input_path / "raw.csv").open(newline="") as fh:
        rows = list(csv.DictReader(fh))

    time_bjd = [float(r["time_bjd"]) for r in rows]
    flux = [float(r["flux"]) for r in rows]

    median_flux = statistics.median(flux)
    flux_normalized = [v / median_flux for v in flux]

    out = {
        "time_bjd": time_bjd,
        "flux_normalized": flux_normalized,
        "median_flux": median_flux,
        "n_points": len(time_bjd),
    }
    (ctx.step_output_path / "normalized.json").write_text(json.dumps(out, indent=2))
