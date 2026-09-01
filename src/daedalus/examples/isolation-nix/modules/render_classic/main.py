"""isolation-nix / render_classic: transform; renders the word under pyfiglet 1.0.2."""

import json
import os

import daedalus.flow as dae

DECLARED_PIN = "1.0.2"


@dae.entry
def render_classic(ctx: dae.FlowContext) -> None:
    import pyfiglet  # noqa: PLC0415 (lazy: pyfiglet lives in this module's nix env)

    word = json.loads((ctx.step_input_path / "word.json").read_text())["text"]
    report = {
        "branch": "render_classic",
        "declared_pin": DECLARED_PIN,
        "imported_pyfiglet_version": pyfiglet.__version__,
        "art": pyfiglet.figlet_format(word),
        "isolation_marker": os.environ.get("DAE_ISOLATION"),
    }
    (ctx.step_output_path / "report.json").write_text(json.dumps(report, indent=2))
