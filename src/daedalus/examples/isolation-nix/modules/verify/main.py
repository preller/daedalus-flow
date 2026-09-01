"""isolation-nix / verify: walk collector; each branch must import its own pin."""

import json

import daedalus.flow as dae


@dae.entry
def verify(ctx: dae.FlowContext) -> None:
    reports = {}
    for branch_dir in ctx.walk_inputs.values():
        report = json.loads((branch_dir / "report.json").read_text())
        reports[report["branch"]] = report

    classic = reports["render_classic"]
    modern = reports["render_modern"]
    classic_version = classic["imported_pyfiglet_version"]
    modern_version = modern["imported_pyfiglet_version"]

    each_got_its_pin = (
        classic_version == classic["declared_pin"]
        and modern_version == modern["declared_pin"]
    )
    versions_differ = classic_version != modern_version
    isolation_proven = each_got_its_pin and versions_differ

    proof = {
        "render_classic_pyfiglet": classic_version,
        "render_modern_pyfiglet": modern_version,
        "each_module_got_its_pinned_version": each_got_its_pin,
        "the_two_versions_differ": versions_differ,
        "ran_under_nix": (
            classic["isolation_marker"] == "nix" and modern["isolation_marker"] == "nix"
        ),
        "isolation_proven": isolation_proven,
    }
    (ctx.step_output_path / "proof.json").write_text(json.dumps(proof, indent=2))

    if not isolation_proven:
        msg = f"per-module nix version isolation failed: {proof}"
        raise RuntimeError(msg)
