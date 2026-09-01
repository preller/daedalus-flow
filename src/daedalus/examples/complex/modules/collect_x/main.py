"""complex / collect_x: pass-through walk collector."""

import json

import daedalus.flow as dae


@dae.entry
def collect_x(ctx: dae.FlowContext) -> None:
    # Collectors read walk or flight inputs; every other role reads the step input.
    merged = list(ctx.walk_inputs.values()) or list(ctx.flight_inputs.values())
    if merged:
        parts = [json.loads((d / "marker.json").read_text())["path"] for d in merged]
        upstream = "[" + " | ".join(parts) + "]"
    else:
        src = ctx.step_input_path / "marker.json"
        upstream = json.loads(src.read_text())["path"] if src.exists() else ""
    path = f"{upstream}>{ctx.step_id}" if upstream else ctx.step_id

    marker = {
        "module": ctx.step_id,
        "flight_id": ctx.flight_id,
        "walk_id": ctx.walk_id,
        "seed": ctx.seed,
        "path": path,
    }
    (ctx.step_output_path / "marker.json").write_text(
        json.dumps(marker, indent=2, sort_keys=True) + "\n"
    )
