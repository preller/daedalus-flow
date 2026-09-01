"""art, nix_diamond: transform on the right branch; its nix env holds art and not pyfiglet."""

import importlib.util
import json
import os
import sys

import art

import daedalus.flow as dae


@dae.entry
def art_branch(ctx: dae.FlowContext) -> None:
    banner = art.text2art("ART")
    report = {
        "branch": "art",
        "python": sys.version.split()[0],
        "my_lib": "art",
        "my_lib_version": getattr(art, "__version__", "unknown"),
        "can_import_pyfiglet": importlib.util.find_spec("pyfiglet") is not None,
        "can_import_networkx": importlib.util.find_spec("networkx") is not None,
        "isolation_marker": os.environ.get("DAE_ISOLATION"),
        "art": banner,
    }
    (ctx.step_output_path / "report.json").write_text(json.dumps(report, indent=2))
