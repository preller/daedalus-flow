"""``dae lab``: define, inspect and run a Lab.

The Typer group, the five commands and the engine-selection and run chain stay
in this ``__init__`` so ``@lab.command()`` registration runs on import and
``daedalus.cli.commands.lab`` stays the namespace tests patch
(``_prefect_available``). The recipe-to-Outcome analysis lives in ``_validate``
and the Prefect human-output glue in ``_prefect``; neither imports back.
"""

import importlib.util
import shutil
from collections.abc import Callable
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any

import typer

from daedalus.cli import chrome, render, strings
from daedalus.cli.commands._outcome import JsonOption, is_json, resolve
from daedalus.cli.commands.lab._prefect import (
    _announce_prefect_start,
    _print_prefect_run_notes,
    _quiet_prefect_for_json,
)
from daedalus.cli.commands.lab._validate import (
    _VALIDATE_HINT,
    _load_runnable_spec,
    _load_sound_spec,
    _refuse,
    _validate_recipe_path,
    deep_validate,
    isolation_resolution,
    recipe_summary,
)
from daedalus.cli.render import lab_run_plan_payload
from daedalus.core import lineage, paths, recipe, topology
from daedalus.core.engine.local import LocalEngine
from daedalus.core.engine.protocol import (
    ExecutionResult,
    LabConfig,
    OrchestrationEngine,
)
from daedalus.core.outcomes import Outcome


def _within_clean_root(target: Path) -> bool:
    """True when ``target`` resolves under ``.daedalus`` or ``dae-outputs`` in cwd."""
    cwd = Path.cwd().resolve()
    resolved = target.resolve()
    try:
        relative = resolved.relative_to(cwd)
    except ValueError:
        return False
    return bool(relative.parts) and relative.parts[0] in {
        topology.INTERNAL_DIR,
        topology.OUTPUT_ROOT,
    }


lab = typer.Typer(
    help="Define, inspect and run a Lab.",
    no_args_is_help=True,
)


def _lab_skeleton(name: str) -> str:
    """A deterministic, minimal ``lab.yaml`` for a freshly scaffolded Lab."""
    return f"name: {name}\nmodules: []\n"


@lab.command("init")
def init(
    name: str,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Show what would be created; write nothing."),
    ] = False,
    json_out: JsonOption = False,
) -> None:
    """Scaffold a new Lab: <name>/lab.yaml plus its modules/ and dot dir.

    Refuses to clobber an existing <name>/ (dae.lab.init.exists, exit 2).
    --dry-run lists what it would create and writes nothing
    (dae.lab.init.dry_run, exit 0).
    """
    target = paths.lab_dir(name)
    if not paths.is_within_cwd(target):
        raise typer.BadParameter(
            f"lab name must stay within the current directory: {name!r}"
        )
    would_create = [
        target / "lab.yaml",
        target / "modules",
        target / topology.INTERNAL_DIR,
    ]

    if dry_run:
        if not is_json():
            render.preview_banner("lab init preview (--dry-run)")
            render.lab_init(name)
        return resolve(
            Outcome.DAE_LAB_INIT_DRY_RUN,
            payload={"paths": [str(p) for p in would_create]},
        )

    if target.exists():
        if not is_json():
            chrome.note(f"'{name}' already exists here; refusing to overwrite it.")
        return resolve(Outcome.DAE_LAB_INIT_EXISTS)

    (target / "modules").mkdir(parents=True)
    (target / topology.INTERNAL_DIR).mkdir()
    (target / "lab.yaml").write_text(_lab_skeleton(name))
    if not is_json():
        render.lab_init_done(name)
        chrome.next_line(f"dae module create <id>   (add a module to {name})")
        chrome.next_line("dae lab validate   (once the recipe is wired)")
    return resolve(
        Outcome.LAB_INIT_OK, payload={"paths": [str(p) for p in would_create]}
    )


@lab.command("validate")
def validate(
    path: Annotated[
        str | None,
        typer.Argument(help="A lab recipe YAML to check; omit for the exemplar."),
    ] = None,
    deep: Annotated[
        bool,
        typer.Option("--deep", help=strings.VALIDATE_DEEP_HELP),
    ] = False,
    json_out: JsonOption = False,
) -> None:
    """Check a Lab recipe (at most a single emitter, no dangling deps, no cycles).

    With a PATH, the first defect is its dae.lab.validate.* failure (exit 1), an
    unparseable file parse_error (exit 1), a missing file not_found (exit 2) and a
    sound recipe dae.lab.validate.ok. Without a PATH, check ./lab.yaml or the exemplar.
    """

    def _resolve_validated(recipe_path: str) -> None:
        # The recipe is parsed once here, and its isolation pairs read once; a
        # sound one carries its `recipe` summary and per-module resolution, a
        # defect or parse error no payload.
        loaded = _load_sound_spec(recipe_path)
        if isinstance(loaded, Outcome):
            return resolve(loaded)
        spec, pairs = loaded
        lab_dir = Path(recipe_path).parent
        resolution = isolation_resolution(pairs)
        if deep:
            failure = deep_validate(lab_dir, pairs)
            if failure is not None:
                return _resolve_deep_failure(*failure)
        else:
            _nudge_deep(resolution)
        payload = {"recipe": recipe_summary(spec), "resolution": resolution}
        return resolve(Outcome.LAB_VALIDATE_OK, payload=payload)

    if path is not None:
        return _resolve_validated(path)

    # Without a PATH, validate the cwd lab (as `lab run` does) so a broken
    # ./lab.yaml is not masked by the exemplar; the exemplar is the no-lab fallback.
    discovered = recipe.discover_lab(Path.cwd())
    if discovered is not None:
        return _resolve_validated(str(discovered))

    if not is_json():
        render.lab_validate()
        chrome.next_line("dae lab visualize   (see the DAG shape)")
        chrome.next_line("dae lab run --dry-run   (preview the plan)")
    # The exemplar fallback validated no specific recipe; carry recipe: null so the
    # ok envelope always exposes data.recipe, never a vanished key.
    return resolve(
        Outcome.LAB_VALIDATE_OK, payload={"recipe": None, "resolution": None}
    )


def _nudge_deep(resolution: list[dict[str, object]] | None) -> None:
    """Print the --deep nudge when a module resolves to uv or nix (human path only)."""
    if is_json() or resolution is None:
        return
    needs_build = sum(1 for r in resolution if r.get("strategy") in ("uv", "nix"))
    if needs_build:
        chrome.note(strings.validate_deep_nudge(needs_build))


def _resolve_deep_failure(module_id: str, cause: str) -> None:
    """Resolve a --deep probe failure as isolation_unbacked with a load_failed cause."""
    # The probe imports the entry and never calls it, so the cause is a load failure.
    error = {
        "code": str(Outcome.DAE_STEP_LOAD_FAILED),
        "module": module_id,
        "error": cause,
        "reason": cause,
    }
    if not is_json():
        chrome.note(f"deep validate failed at module '{module_id}': {cause}")
    return resolve(Outcome.DAE_LAB_VALIDATE_ISOLATION_UNBACKED, error=error)


class VisualizeStyle(StrEnum):
    """The ``--style`` choices; ``.value`` is the name the render layer reads."""

    table = "table"
    full = "full"
    num = "num"
    rolenum = "rolenum"


StyleOption = Annotated[
    VisualizeStyle,
    typer.Option(
        "--style",
        help="Show the recipe as a table (default) or a graph (full / num / rolenum).",
    ),
]


def _draw_graph_view(payload: dict[str, Any], style: VisualizeStyle) -> None:
    """Draw a graph ``--style``; a missing viz extra becomes one stderr note."""
    try:
        render.lab_visualize_graph(payload, style=style.value)
    except render.GraphLayoutUnavailable as exc:
        chrome.note(str(exc))


def _show_visualize(
    payload: dict[str, Any],
    style: VisualizeStyle,
    table_render: Callable[[], None],
) -> None:
    """Render the human visualize view for ``style``, then the Next hint."""
    if style is VisualizeStyle.table:
        table_render()
        chrome.note(
            "for a graph view, run 'dae lab visualize --style full' (or num / rolenum)."
        )
    else:
        _draw_graph_view(payload, style)
    chrome.next_line("dae lab run --dry-run   (preview the plan)")


@lab.command("visualize")
def visualize(
    style: StyleOption = VisualizeStyle.table,
    json_out: JsonOption = False,
) -> None:
    """Show the Lab's recipe as a topology table (default) or a boxed ASCII graph.

    --style full / num / rolenum draw the graph (needs the viz extra); --json
    emits one payload for every style. With a ./lab.yaml in cwd, draw that lab,
    or its "dae lab validate" verdict when it cannot be drawn; else the exemplar.
    """
    discovered = recipe.discover_lab(Path.cwd())
    if discovered is None:
        payload = render.visualize_payload()
        if not is_json():
            _show_visualize(payload, style, render.lab_visualize)
        return resolve(Outcome.LAB_VISUALIZE_OK, payload=payload)

    import networkx as nx  # noqa: PLC0415 (lazy: off the dae --help path)

    from daedalus.core import dag, walks  # noqa: PLC0415

    # A cwd lab that yields no role-bearing acyclic graph is not drawable;
    # resolve to the verdict `dae lab validate` gives, not a traceback.
    try:
        spec = recipe.load_recipe(discovered)
        graph = dag.build_dag(spec, discovered.parent, with_roles=True)
    except recipe.RecipeParseError:
        return resolve(_validate_recipe_path(str(discovered)))
    if not nx.is_directed_acyclic_graph(graph):
        return resolve(_validate_recipe_path(str(discovered)))

    # A walk-defective lab (incomplete collector group, budget overflow) is not
    # drawable either; resolve to the validate verdict the token pass owns.
    walk_plan = walks.propagate(spec, discovered.parent)
    if isinstance(walk_plan, walks.WalkDefect):
        return resolve(_validate_recipe_path(str(discovered)))

    lab_name = spec.name or discovered.parent.name
    payload = render.visualize_payload_for(graph, walk_plan)
    if not is_json():
        _show_visualize(
            payload, style, lambda: render.lab_visualize_for(graph, lab_name, walk_plan)
        )
    return resolve(Outcome.LAB_VISUALIZE_OK, payload=payload)


@lab.command("run")
def run(
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Preview the plan; run nothing.")
    ] = False,
    json_out: JsonOption = False,
) -> None:
    """Run the whole Lab end to end on the local engine.

    Serial unless max_workers > 1 in lab.yaml; any valid DAG runs. Exit 2 when
    ./lab.yaml is missing, invalid (see "dae lab validate") or a multi-parent
    broadcast; exit 1 when a module raises. --dry-run shows the plan, writes nothing.
    """
    cwd = Path.cwd()
    lab_path = recipe.discover_lab(cwd)
    if lab_path is None:
        return resolve(
            _refuse(
                Outcome.DAE_LAB_RUN_NOT_FOUND,
                "no lab.yaml in this directory (run 'dae lab init <name>').",
            )
        )

    spec_or_outcome = _load_runnable_spec(lab_path)
    if isinstance(spec_or_outcome, Outcome):
        return resolve(spec_or_outcome)
    lab_dir = lab_path.parent

    config = LabConfig(
        lab_name=spec_or_outcome.name or lab_dir.name,
        lab_dir=lab_dir,
        seed=0,
        output_root=cwd / topology.OUTPUT_ROOT,
        max_workers=spec_or_outcome.max_workers,
        engine=spec_or_outcome.engine,
        isolation=spec_or_outcome.isolation,
    )
    try:
        plan = recipe.build_plan(spec_or_outcome, lab_dir)
    except recipe.RecipeParseError as error:
        return resolve(
            _refuse(
                Outcome.DAE_LAB_RUN_INVALID,
                f"{error.message} ({_VALIDATE_HINT}).",
            )
        )

    if dry_run:
        if not is_json():
            render.preview_banner("plan preview (--dry-run)")
            render.lab_run_plan(plan)
            chrome.next_line("dae lab run   (execute the plan for real)")
        return resolve(Outcome.LAB_RUN_DRY_RUN, payload=lab_run_plan_payload(plan))

    return _execute_and_resolve(plan, config)


# Stays in this __init__ so the `_prefect_available` test patch resolves
# through `daedalus.cli.commands.lab`.
def _prefect_available() -> bool:
    """True when the optional ``prefect`` extra is importable (``find_spec`` only)."""
    # find_spec does not import prefect, whose cold import takes seconds.
    return importlib.util.find_spec("prefect") is not None


def _select_engine(engine_name: str) -> OrchestrationEngine | None:
    """The engine the lab selected, or None when the prefect extra is absent."""
    if engine_name == "prefect":
        if not _prefect_available():
            return None
        # Imported here so the LocalEngine path never loads the prefect adapter.
        from daedalus.core.engine.prefect import PrefectEngine  # noqa: PLC0415

        return PrefectEngine()
    return LocalEngine()


def _isolation_precondition(
    plan: recipe.ExecutionPlan, config: LabConfig
) -> Outcome | None:
    """Refuse with isolation_unavailable when a resolved backend cannot run here."""
    from daedalus.core.engine.isolation import (  # noqa: PLC0415 (lazy)
        ModuleEnv,
        resolve_plan,
        strategy_for,
    )

    envs = [
        ModuleEnv.from_module_dir(step.module_id, step.module_dir)
        for step in plan.steps
    ]
    resolutions = resolve_plan(envs, config.isolation, config.max_workers)
    # Each distinct strategy is probed once; only nix can be unavailable.
    for name in {resolution.strategy for resolution in resolutions}:
        if not strategy_for(name).available():
            return _refuse(
                Outcome.DAE_LAB_RUN_ISOLATION_UNAVAILABLE,
                strings.ISOLATION_UNAVAILABLE_HINT,
            )
    return None


def _reconcile_prior_flow(output_root: Path) -> None:
    """Flip a prior flow stranded as running/submitted to failed, best effort."""
    flow_ids = lineage.list_flows(output_root)
    if not flow_ids:
        return
    try:
        lineage.read_flow_record_reconciled(output_root / "flows" / flow_ids[-1])
    except lineage.LineageError:
        # A missing or unreadable prior record must not block a fresh run.
        return


def _execute_and_resolve(plan: recipe.ExecutionPlan, config: LabConfig) -> None:
    """Run the plan on the selected engine, render the result, resolve the code."""
    engine = _select_engine(config.engine)
    if engine is None:
        # The [engine] extra is absent for engine: prefect; refuse before any write.
        return resolve(
            _refuse(
                Outcome.DAE_LAB_RUN_ENGINE_UNAVAILABLE,
                strings.ENGINE_UNAVAILABLE_HINT,
            )
        )
    isolation_refusal = _isolation_precondition(plan, config)
    if isolation_refusal is not None:
        # nix is unusable on this host; refuse before any write, no fallback to uv.
        return resolve(isolation_refusal)
    _quiet_prefect_for_json(config)
    _announce_prefect_start(config)
    _reconcile_prior_flow(config.output_root)
    result = engine.execute_dag(plan, config)
    flow_dir = config.output_root / "flows" / result.flow_id
    record = lineage.read_flow_record(flow_dir)
    payload = render.flow_status_payload(record)
    cause = render.failure_cause(record)

    if not is_json():
        render.lab_run_result(result, record, flow_dir)
        _print_prefect_run_notes(config, result)
    if result.missing_package is not None:
        # A module's third-party dep is absent. Point at the module's
        # requirements.txt instead of the raw ModuleNotFoundError.
        note = strings.MISSING_DEPS_HINT.format(
            module_id=_failed_module(record), pkg=result.missing_package
        )
        if not is_json():
            chrome.note(note)
        return resolve(Outcome.DAE_LAB_RUN_MISSING_DEPS, payload=payload, error=cause)
    if result.error is not None:
        if not is_json():
            chrome.note(f"run failed at step '{_failed_step(record)}': {result.error}")
        return resolve(Outcome.DAE_LAB_RUN_FAILED, payload=payload, error=cause)
    return _resolve_success(result, payload)


def _resolve_success(result: ExecutionResult, payload: dict[str, Any]) -> None:
    """Resolve a completed run as ok_empty for an empty partition, else lab.run.ok."""
    if result.empty_partition:
        if not is_json():
            chrome.note(
                "emitter yielded an empty partition: 0 flights, nothing to run."
            )
        return resolve(Outcome.DAE_LAB_RUN_OK_EMPTY, payload=payload)
    if not is_json():
        chrome.next_line("dae flow status   (inspect the Flow)")
    return resolve(Outcome.LAB_RUN_OK, payload=payload)


def _failed_step(record: lineage.FlowRecord) -> str:
    """The id of the first failed step in a flow record (for the failure note)."""
    for step in record.steps:
        if step.status == "failed":
            return step.step_id
    return "(unknown)"


def _failed_module(record: lineage.FlowRecord) -> str:
    """The module id of the first failed step, without its ``@w<n>`` suffix."""
    # "(unknown)" has no "@" and passes through unchanged.
    module_id, _, _ = _failed_step(record).rpartition("@")
    return module_id or _failed_step(record)


@lab.command("clean")
def clean(
    name: Annotated[
        str | None,
        typer.Argument(help="Remove only this subtree of the two roots."),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="List what would be removed; remove nothing."),
    ] = False,
    json_out: JsonOption = False,
) -> None:
    """Remove generated artifacts, only .daedalus/ and dae-outputs/ in cwd.

    An optional name scopes removal to that subtree of each root. --dry-run lists
    and removes nothing (dae.lab.clean.dry_run); a real run is dae.lab.clean.ok and
    an empty cwd dae.lab.clean.nothing, all exit 0. --json lists 'paths'.
    """
    roots = paths.clean_roots()
    targets = [root / name for root in roots] if name is not None else roots
    present = [t for t in targets if _within_clean_root(t) and t.exists()]

    if dry_run:
        if not is_json():
            render.preview_banner("lab clean preview (--dry-run)")
            chrome.note(f"would remove {len(present)} item(s) (see --json for paths).")
        return resolve(
            Outcome.DAE_LAB_CLEAN_DRY_RUN,
            payload={"paths": [str(t) for t in present]},
        )

    if not present:
        if not is_json():
            chrome.note("nothing to clean; no .daedalus/ or dae-outputs/ here.")
        return resolve(Outcome.DAE_LAB_CLEAN_NOTHING)

    removed = []
    for target in present:
        shutil.rmtree(target)
        removed.append(str(target))
    if not is_json():
        chrome.note(f"removed {len(removed)} item(s) (see --json for paths).")
    return resolve(Outcome.DAE_LAB_CLEAN_OK, payload={"paths": removed})
