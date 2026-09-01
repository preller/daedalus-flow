"""emit_ticks, linear_smoke: emitter that writes n_ticks values derived from ctx.seed alone."""

import json

import daedalus.flow as dae


@dae.entry
def emit_ticks(ctx: dae.FlowContext) -> None:
    payload = json.loads((ctx.step_input_path / "seed.json").read_text())
    n_ticks = int(payload["n_ticks"])

    # A seeded recurrence in the stdlib alone, stable across processes and platforms.
    ticks = [(ctx.seed + index * 7) % 100 for index in range(n_ticks)]

    out = {"ticks": ticks, "seed": ctx.seed}
    (ctx.step_output_path / "ticks.json").write_text(json.dumps(out, indent=2))
