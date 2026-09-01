"""collect_results, exoplanet_validation: the sink transform; files the run into a stable results/ tree."""

import json
import shutil

import daedalus.flow as dae

PER_TARGET_FILES = (
    "distances.json",
    "corner_data.json",
    "corner.png",
    "overlay_data.json",
    "overlay.png",
)


@dae.entry
def collect_results(ctx: dae.FlowContext) -> None:
    # Copy the converged run, plots included, into a stable results/ tree.
    comparison = json.loads((ctx.step_input_path / "comparison.json").read_text())

    results = ctx.step_output_path / "results"
    targets_root = results / "targets"
    targets_root.mkdir(parents=True, exist_ok=True)

    shutil.copy2(ctx.step_input_path / "comparison.json", results / "summary.json")

    for target in comparison["targets"]:
        src = ctx.step_input_path / target
        dest = targets_root / target
        dest.mkdir(parents=True, exist_ok=True)
        for name in PER_TARGET_FILES:
            shutil.copy2(src / name, dest / name)
