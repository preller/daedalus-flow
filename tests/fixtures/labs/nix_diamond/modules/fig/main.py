"""fig, nix_diamond: transform on the left branch; its nix env holds pyfiglet and not art."""

import importlib.util
import json
import os
import sys

import pyfiglet

import daedalus.flow as dae


@dae.entry
def fig(ctx: dae.FlowContext) -> None:
    art = pyfiglet.figlet_format("FIG")
    report = {
        "branch": "fig",
        "python": sys.version.split()[0],
        "my_lib": "pyfiglet",
        "my_lib_version": getattr(pyfiglet, "__version__", "unknown"),
        "can_import_art": importlib.util.find_spec("art") is not None,
        "can_import_networkx": importlib.util.find_spec("networkx") is not None,
        "isolation_marker": os.environ.get("DAE_ISOLATION"),
        "art": art,
    }
    (ctx.step_output_path / "report.json").write_text(json.dumps(report, indent=2))
