"""module_H, complex: pass-through shape fixture (transform); see tests/fixtures/README.md."""

import json

import daedalus.flow as dae


@dae.entry
def module_H(ctx: dae.FlowContext) -> None:
    # A collector reads its walk or flight inputs; any other role reads its upstream.
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
