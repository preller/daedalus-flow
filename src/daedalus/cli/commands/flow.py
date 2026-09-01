"""Inspect the latest flow and resume a failed one (the ``flow`` command group).

``status`` reads the lineage the engine wrote under ``dae-outputs/flows/`` in
cwd and renders the latest flow; it returns ``dae.flow.status.ok``, or
``dae.flow.status.nothing`` (exit 0) when there is none. ``resume`` replays the
recorded plan of the latest failed flow through ``LocalEngine.resume_flow``,
skipping completed steps; it returns ``dae.flow.resume.ok``, ``.nothing``
(exit 0) or ``.failed`` (the re-run failed again).
"""

from pathlib import Path

import typer

from daedalus.cli import chrome, render
from daedalus.cli.commands._outcome import JsonOption, is_json, resolve
from daedalus.core import lineage, topology
from daedalus.core.outcomes import Outcome

flow = typer.Typer(
    help="Inspect a flow run; resume a failed flow.", no_args_is_help=True
)


def _note(message: str) -> None:
    """Write a stderr note only on the human (non-json) surface."""
    if not is_json():
        chrome.note(message)


@flow.command()
def status(json_out: JsonOption = False) -> None:
    """Show the latest flow's lineage from dae-outputs/flows/ in cwd.

    No flow here is dae.flow.status.nothing (exit 0), not an error. status is
    read-only and exits 0 even for a failed flow, which names its cause in the
    envelope error slot; act on a failure with 'dae flow resume'.
    """
    output_root = Path.cwd() / topology.OUTPUT_ROOT
    flow_ids = lineage.list_flows(output_root)
    if not flow_ids:
        _note("no flows here yet (run 'dae lab run' first).")
        return resolve(Outcome.DAE_FLOW_STATUS_NOTHING)

    latest = flow_ids[-1]
    # A run stranded as `running`/`submitted` by a crash is flipped to `failed`
    # on read, so status never reports a dead run as alive.
    record = lineage.read_flow_record_reconciled(output_root / "flows" / latest)
    if not is_json():
        render.flow_status(record)
        # resume only re-runs failed steps, so the hint appears for a failed flow.
        if record.status == "failed":
            chrome.next_line("dae flow resume   (re-run only the steps that need it)")
    return resolve(
        Outcome.FLOW_STATUS_OK,
        payload=render.flow_status_payload(record),
        error=render.failure_cause(record),
    )


@flow.command()
def resume(json_out: JsonOption = False) -> None:
    """Resume the latest failed flow, re-running the failed step and what follows it.

    Completed steps are skipped and their artifacts reused. With no flow, or the
    latest completed, there is nothing to resume (dae.flow.resume.nothing, exit 0);
    a re-run that fails again is .failed (exit 1). Edits since are not re-validated.
    """
    # Lazy (off the bare `dae --help` path): recipe + engine pull networkx.
    from daedalus.core import recipe  # noqa: PLC0415
    from daedalus.core.engine import LabConfig, LocalEngine  # noqa: PLC0415

    cwd = Path.cwd()
    output_root = cwd / topology.OUTPUT_ROOT
    flow_ids = lineage.list_flows(output_root)
    if not flow_ids:
        _note("no flows here to resume (run 'dae lab run' first).")
        return resolve(Outcome.DAE_FLOW_RESUME_NOTHING)

    latest = flow_ids[-1]
    record = lineage.read_flow_record(output_root / "flows" / latest)
    if record.status != "failed":
        _note(f"latest flow '{latest}' is {record.status}; nothing to resume.")
        return resolve(Outcome.DAE_FLOW_RESUME_NOTHING)

    lab_path = recipe.discover_lab(cwd)
    if lab_path is None:
        _note("no lab.yaml here to resume against.")
        return resolve(Outcome.DAE_FLOW_RESUME_NOTHING)
    lab_dir = lab_path.parent
    try:
        spec = recipe.load_recipe(lab_path)
        plan = recipe.build_plan(spec, lab_dir)
    except recipe.RecipeParseError:
        # The lab no longer parses or builds (a structural edit since the run); it
        # cannot be resumed against, and the note says so.
        _note("this lab no longer builds a valid plan; cannot resume it.")
        return resolve(Outcome.DAE_FLOW_RESUME_NOTHING)

    config = LabConfig(
        lab_name=spec.name or lab_dir.name,
        lab_dir=lab_dir,
        seed=0,
        output_root=output_root,
        max_workers=spec.max_workers,
        engine=spec.engine,
        isolation=spec.isolation,
    )
    result = LocalEngine().resume_flow(plan, config, latest)

    record = lineage.read_flow_record(output_root / "flows" / latest)
    payload = render.flow_status_payload(record)
    if not is_json():
        render.flow_status(record)
    _note(
        "resume replayed the recorded plan; module / recipe edits since the "
        "failed run were not re-validated."
    )
    if result.error is not None:
        _note(f"resume still failed at a step: {result.error}")
        return resolve(
            Outcome.DAE_FLOW_RESUME_FAILED,
            payload=payload,
            error=render.failure_cause(record),
        )
    return resolve(Outcome.FLOW_RESUME_OK, payload=payload)
