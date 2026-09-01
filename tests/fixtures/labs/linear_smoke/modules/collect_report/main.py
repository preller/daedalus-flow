"""collect_report, linear_smoke: flight_collector that writes run_report.json naming every upstream step."""

import json

import daedalus.flow as dae

# The upstream chain this report summarizes, in run order. Named explicitly so
# the final artifact lists every step the linear flow executed.
UPSTREAM_STEPS = [
    "emit_ticks",
    "debug_io",
    "sleep_briefly",
    "summarize_walk",
]


@dae.entry
def collect_report(ctx: dae.FlowContext) -> None:
    # Exactly one flight in a linear flow; read it by content, not by dict key.
    (flight_dir,) = ctx.flight_inputs.values()
    summary = json.loads((flight_dir / "walk_summary.json").read_text())

    report = {
        "lab": "linear_smoke",
        "upstream_steps": [*UPSTREAM_STEPS, ctx.step_id],
        "n_ticks": summary["n_ticks"],
        "sum": summary["sum"],
    }
    (ctx.step_output_path / "run_report.json").write_text(json.dumps(report, indent=2))
