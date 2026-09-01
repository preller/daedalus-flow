"""merge_walks: walk_collector fixture; sums part.json values keyed by each payload's walk field; see tests/fixtures/README.md."""

import json

import numpy as np

import daedalus.flow as dae


@dae.entry
def merge_walks(ctx: dae.FlowContext) -> None:
    # Collect (walk, value) pairs from every walk input, keyed by payload.
    pairs = []
    for walk_dir in ctx.walk_inputs.values():
        payload = json.loads((walk_dir / "part.json").read_text())
        pairs.append((payload["walk"], payload["value"]))

    # Sort by walk key for stable, order-independent output.
    pairs.sort(key=lambda pair: pair[0])
    per_walk = {walk: value for walk, value in pairs}

    # Exact integer sum (int cast keeps numpy out of the JSON).
    total = int(np.sum([value for _, value in pairs]))

    merged = {"per_walk": per_walk, "total": total}
    (ctx.step_output_path / "merged.json").write_text(json.dumps(merged, indent=2))
