"""join, nix_diamond: walk_collector that merges both branch reports into joined.json."""

import json

import daedalus.flow as dae


@dae.entry
def join(ctx: dae.FlowContext) -> None:
    branches = {}
    for branch_dir in ctx.walk_inputs.values():
        r = json.loads((branch_dir / "report.json").read_text())
        other = "art" if r["branch"] == "fig" else "pyfiglet"
        branches[r["branch"]] = {
            "my_lib": r["my_lib"],
            "my_lib_version": r["my_lib_version"],
            "sees_sibling_lib": r.get("can_import_" + other),
            "sees_host_only_networkx": r.get("can_import_networkx"),
            "isolation_marker": r.get("isolation_marker"),
        }
    joined = {"modules": sorted(branches), "branches": branches}
    (ctx.step_output_path / "joined.json").write_text(json.dumps(joined, indent=2))
