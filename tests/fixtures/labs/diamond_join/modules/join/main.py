"""join, diamond_join: walk_collector that sums both branch values, keyed by each payload's branch field."""

import json

import daedalus.flow as dae


@dae.entry
def join(ctx: dae.FlowContext) -> None:
    # ctx.walk_inputs holds both branches; key each value by its payload's branch field.
    pairs = []
    for branch_dir in ctx.walk_inputs.values():
        payload = json.loads((branch_dir / "value.json").read_text())
        pairs.append((payload["branch"], payload["value"]))

    # Sort by branch for stable, order-independent output.
    pairs.sort(key=lambda pair: pair[0])
    per_branch = {branch: value for branch, value in pairs}
    total = sum(value for _, value in pairs)

    joined = {"per_branch": per_branch, "sum": total}
    (ctx.step_output_path / "joined.json").write_text(json.dumps(joined, indent=2))
