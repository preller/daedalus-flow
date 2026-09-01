"""Render the structural reports and build their ``--json`` payloads.

The lab-validate listing, the static recipe table, the run-plan and run-result
tables and the flow-status table, plus the payload builders that read the same
topology data as the tables. Composes ``report_header``, ``_glyph_cell`` and
``_role_legend`` from ``_base``. ``networkx`` is imported inside the functions
that need it, off the ``dae --help`` path.
"""

from collections.abc import Callable, Iterable
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from rich import box
from rich.measure import Measurement
from rich.table import Table
from rich.text import Text

from daedalus.cli import strings
from daedalus.cli.console import ROLE_GLYPH, ROLE_STYLE, out
from daedalus.core import topology
from daedalus.core.engine.protocol import ExecutionResult
from daedalus.core.lineage import FlowRecord, WalkRecord
from daedalus.core.recipe import ExecutionPlan
from daedalus.flow import Role

from ._ascii_dag import Palette, Style, dag_legend, draw_dag
from ._base import _glyph_cell, _role_legend, report_header

if TYPE_CHECKING:
    import networkx as nx

    from daedalus.core.walks import WalkPlan


def _fanout_note() -> Text:
    """The note under the static views that module counts expand at run time."""
    return Text(
        "these are the recipe's modules; at run time each fanned module "
        "expands by its input rows into more step instances. "
        "Run `dae lab run` to materialize them.",
        style="muted",
    )


def _framed_table(title: str, table: Table) -> None:
    """Print a header whose underline matches the table's content width."""
    width = Measurement.get(out, out.options, table).maximum
    out.print(Text(title, style="header"))
    out.print(Text("─" * width, style="muted"))
    out.print(table)


def _lab_relative_dir(module_dir: Path) -> str:
    """The ``modules/<id>`` leaf of a module dir; the basename when not under it."""
    parts = module_dir.parts
    if "modules" in parts:
        return str(Path(*parts[parts.index("modules") :]))
    return module_dir.name


def _user_label_of(walk_id: str, walks: tuple[WalkRecord, ...]) -> str | None:
    """The ``walk_J`` / ``flight_K`` label of a walk token; None for the root walk."""
    # TODO: label flight steps by target name; it lives in the module output
    # (summary.json), not in the lineage record.
    record = next((w for w in walks if w.walk_id == walk_id), None)
    if record is None:
        return None
    if record.user_walk is not None:
        return record.user_walk
    if record.flight_id is not None:
        return f"flight_{record.flight_id[1:]}"
    return None


def _step_label(step_id: str, walks: tuple[WalkRecord, ...]) -> Text:
    """A step id with its ``[walk_J]`` / ``[flight_K]`` tag appended in muted style."""
    label = Text(step_id)
    walk_id = step_id.rsplit("@", 1)[-1] if "@" in step_id else None
    user = _user_label_of(walk_id, walks) if walk_id is not None else None
    if user is not None:
        label.append(f"  [{user}]", style="muted")
    return label


def lab_validate() -> None:
    """Print the valid-lab report, a header plus the node and glyph listing."""
    body = Text()
    body.append(f"Lab valid - {topology.LAB}\n", style="ok")
    body.append(f"  {len(topology.NODES)} nodes, no cycles\n\n", style="muted")
    for mod, role in topology.ranked():
        body.append("    ")
        body.append_text(_glyph_cell(role))
        body.append(f"  {mod}\n")
    out.print(body)
    out.print(_role_legend())


def _recipe_table() -> Table:
    """A borderless table whose first two columns are the ordinal and role glyph."""
    table = Table(box=box.SIMPLE, pad_edge=False, show_edge=False)
    table.add_column("#", style="muted", justify="right")
    table.add_column("", justify="center")
    return table


def _topology_graph() -> "nx.DiGraph":
    """The exemplar topology as a fresh DiGraph, nodes first, then edges."""
    import networkx as nx  # noqa: PLC0415 (lazy: off the dae --help path)

    graph = nx.DiGraph()
    graph.add_nodes_from(node for node, _ in topology.NODES)
    graph.add_edges_from(topology.EDGES)
    return graph


def _flight_scoped_nodes(
    graph: "nx.DiGraph", role_of: Callable[[str], object]
) -> frozenset[str]:
    """Node ids strictly between an emitter and a flight_collector, the ``~`` band."""
    import networkx as nx  # noqa: PLC0415 (lazy: off the dae --help path)

    # role_of may return a Role or its on-disk string; Role is a StrEnum, so
    # the comparison holds either way.
    emitters = [node for node in graph if role_of(node) == Role.EMITTER]
    collectors = [node for node in graph if role_of(node) == Role.FLIGHT_COLLECTOR]
    if not emitters or not collectors:
        return frozenset()
    below: set[str] = set().union(*(nx.descendants(graph, e) for e in emitters))
    above: set[str] = set().union(*(nx.ancestors(graph, c) for c in collectors))
    return frozenset(below & above)


def _toposort_layers() -> list[tuple[str, Role, int]]:
    """Exemplar nodes as ``(id, role, layer)``, id-sorted within each generation."""
    import networkx as nx  # noqa: PLC0415 (lazy: off the dae --help path)

    graph = _topology_graph()
    # topological_generations yields unordered sets; sorting each one keeps the
    # row order stable and equal to lexicographical_topological_sort(key=str).
    generations = [sorted(gen) for gen in nx.topological_generations(graph)]
    return [
        (node, topology.role_of(node), layer)
        for layer, gen in enumerate(generations)
        for node in gen
    ]


def _render_recipe_table(
    rows: Iterable[tuple[str, Role, int, list[str]]], title: str
) -> None:
    """Frame the static recipe table built from ``(mod, role, layer, feeds)`` rows."""
    table = _recipe_table()
    table.add_column("layer", style="muted", justify="right")
    table.add_column("node")
    table.add_column("feeds-into", style="muted")
    for i, (mod, role, layer, downstream) in enumerate(rows, start=1):
        feeds = ", ".join(downstream) if downstream else "-  (sink)"
        table.add_row(f"{i:02d}", _glyph_cell(role), str(layer), Text(mod), Text(feeds))
    _framed_table(title, table)


def lab_visualize() -> None:
    """Print the exemplar recipe as a table of ordinal, role glyph, layer, node, feeds.

    One row per module in lexicographical toposort order with its dependency
    layer. Runtime walk and flight fan-out is not drawn or counted here.
    """
    rows = (
        (mod, role, layer, topology.feeds_into(mod))
        for mod, role, layer in _toposort_layers()
    )
    count = topology.STEP_COUNT
    _render_recipe_table(
        rows, f"Lab: {topology.LAB}   ({count} module{'s' if count != 1 else ''})"
    )

    out.print(_role_legend())
    flow = Text(f"source: {topology.source()}", style="muted")
    flow.append(f"   sink: {topology.sink()}", style="muted")
    out.print(flow)
    out.print(_fanout_note())


def _role_glyph_str(role: str) -> Text:
    """The glyph Text for a role string; an unknown role renders as a transform."""
    try:
        flow_role = Role(role)
    except ValueError:
        flow_role = Role.TRANSFORM
    return Text(ROLE_GLYPH[flow_role], style=ROLE_STYLE[flow_role])


def lab_run_plan(plan: ExecutionPlan) -> None:
    """Print the resolved plan as a step table, then the dry-run note.

    The command prints the preview banner. No lineage or flow id appears, since
    a dry run never reaches the engine.
    """
    lab_name = plan.lab_name or "(unnamed lab)"
    count = len(plan.steps)
    table = _recipe_table()
    table.add_column("module")
    # The lab-relative `modules/<id>` leaf; an absolute path head-truncates the
    # varying part at any realistic width.
    table.add_column("module dir (in lab)", style="muted")
    for step in plan.steps:
        table.add_row(
            f"{step.index:02d}",
            _role_glyph_str(step.role),
            Text(step.module_id),
            Text(_lab_relative_dir(step.module_dir), style="muted"),
        )
    # The plan lists recipe modules, not step instances; the fan-out note
    # explains how they expand at run time.
    _framed_table(
        f"Lab: {lab_name}   whole-lab run plan   "
        f"({count} module{'s' if count != 1 else ''})",
        table,
    )
    out.print(Text(strings.DRY_RUN_NO_WRITE, style="muted"))
    out.print(_fanout_note())


def _print_path_line(label: str, path: Path) -> None:
    """Print ``label: <path>`` on one line, unwrapped at any width."""
    out.print(
        Text(f"  {label}{path}", style="muted", no_wrap=True),
        overflow="ignore",
        crop=False,
    )


def _serial_footer(record: FlowRecord) -> None:
    """Print the serial-run note for a local run at max_workers 1."""
    if record.engine == "local" and record.max_workers == 1:
        out.print(Text(strings.SERIAL_RUN_NOTE, style="muted"))


def _failed_step_log(step_id: str) -> Path | None:
    """The ``step-error.log`` of the failed step under cwd, or None when not written."""
    from daedalus.core.engine.local._instance import (  # noqa: PLC0415 (avoid cycle)
        STEP_ERROR_LOG_NAME,
    )

    module_id = step_id.rpartition("@")[0] or step_id
    store = Path.cwd() / ".daedalus"
    if not store.is_dir():
        return None
    for log in sorted(store.rglob(STEP_ERROR_LOG_NAME)):
        if log.parent.name.endswith(f"_{module_id}"):
            return log
    return None


def _print_failure_block(record: FlowRecord) -> None:
    """Print the failed step's code, cause, last traceback frame and log path."""
    failed = next((step for step in record.steps if step.status == "failed"), None)
    if failed is None or failed.error is None:
        return
    if failed.error_code is not None:
        out.print(Text(f"  {failed.error_code}: {failed.error}", style="muted"))
    else:
        out.print(Text(f"  {failed.error}", style="muted"))
    log = _failed_step_log(failed.step_id)
    if log is not None:
        frame = distill_step_traceback(log.read_text())
        out.print(Text(frame, style="muted"), overflow="ignore", crop=False)
        _print_path_line("full traceback: ", log)


def lab_run_result(result: ExecutionResult, record: FlowRecord, flow_dir: Path) -> None:
    """Print the run outcome, the instance count and the result and lineage paths.

    Reads the on-disk flow record. A failed run adds the failure block and the
    count of instances completed before it; the per-step table lives in
    ``dae flow status``.
    """
    total = len(record.steps)
    completed = sum(1 for step in record.steps if step.status == "completed")
    out.print(
        report_header(
            f"Flow: {result.flow_id}   {result.status}   "
            f"({total} {strings.STEP_INSTANCE}{'s' if total != 1 else ''})"
        )
    )

    summary = Text(
        f"  {completed}/{total} {strings.STEP_INSTANCE}s completed", style="muted"
    )
    out.print(summary)

    if result.status == "failed":
        _print_failure_block(record)

    # On a completed flow, name the canonical result: the flow-level final/ dir the
    # sink writes (topology.FINAL_DIR). Gated on the dir existing, so a suppressed
    # copy failure shows no line rather than a path to nothing.
    final_dir = flow_dir / topology.FINAL_DIR
    if result.status == "completed" and final_dir.exists():
        _print_path_line(strings.RESULTS_LABEL, final_dir)
    _print_path_line("lineage: ", flow_dir)
    _serial_footer(record)


# The --json payloads are plain json-safe dicts built from the same topology
# data as the tables above, so the two views describe one graph.


def visualize_payload() -> dict[str, Any]:
    """The exemplar topology as a json-safe dict for ``dae --json lab visualize``.

    Nodes are in lexicographical toposort order with their ``layer`` index; no
    fan-out counts. The walk keys are present but null, so the payload has the
    same key set as :func:`visualize_payload_for`.
    """
    scoped = _flight_scoped_nodes(_topology_graph(), topology.role_of)
    nodes = [
        {"id": mod, "role": str(role), "layer": layer, "flight_scoped": mod in scoped}
        for mod, role, layer in _toposort_layers()
    ]
    return {
        "topology": {
            "nodes": nodes,
            "edges": [[src, dst] for src, dst in topology.EDGES],
            "source": topology.source(),
            "sink": topology.sink(),
        },
        "walks": None,
        "walk_lines": None,
        "token_walk_lines": None,
    }


def _layers_of(graph: "nx.DiGraph") -> list[tuple[str, topology.Role, int]]:
    """``(node, role, layer)`` for a role-bearing acyclic graph, in toposort order."""
    import networkx as nx  # noqa: PLC0415 (lazy: off the dae --help path)

    order = list(nx.lexicographical_topological_sort(graph, key=str))
    # Sort each generation so the layer index is stable across runs.
    generations = [sorted(gen) for gen in nx.topological_generations(graph)]
    layer_of = {node: index for index, gen in enumerate(generations) for node in gen}
    return [
        (node, topology.Role(graph.nodes[node]["role"]), layer_of[node])
        for node in order
    ]


def _graph_endpoints(graph: "nx.DiGraph") -> tuple[str | None, str | None]:
    """The lexicographically first source (in-degree 0) and sink (out-degree 0)."""
    sources = sorted(node for node in graph if graph.in_degree(node) == 0)
    sinks = sorted(node for node in graph if graph.out_degree(node) == 0)
    return (sources[0] if sources else None, sinks[0] if sinks else None)


def lab_visualize_for(
    graph: "nx.DiGraph", lab_name: str, walk_plan: "WalkPlan"
) -> None:
    """Print the recipe table for a cwd lab graph, then its walk lines and legend.

    Same table as :func:`lab_visualize`, driven by ``graph`` instead of the
    exemplar data, followed by one walk string per terminal trace.
    """
    rows = (
        (mod, role, layer, sorted(graph.successors(mod)))
        for mod, role, layer in _layers_of(graph)
    )
    count = graph.number_of_nodes()
    _render_recipe_table(
        rows, f"Lab: {lab_name}   ({count} module{'s' if count != 1 else ''})"
    )

    out.print(_role_legend())
    source, sink = _graph_endpoints(graph)
    flow = Text(f"source: {source or '-'}", style="muted")
    flow.append(f"   sink: {sink or '-'}", style="muted")
    out.print(flow)

    out.print(Text(""))
    out.print(Text("walks", style="muted"))
    for line in walk_plan.config_lines():
        out.print(Text(line))
    # the walk lines use {} / () / [] notation the node-table role legend
    # does not cover; print a second legend keyed to those glyphs.
    out.print(Text(strings.WALK_GLYPH_LEGEND, style="muted"))
    out.print(_fanout_note())


def lab_visualize_graph(payload: dict[str, Any], *, style: str) -> None:
    """Draw a visualize payload as a boxed ASCII DAG for the ``--style`` graph views.

    Prints the legend, the graph, the source and sink line and the fan-out note;
    color is on only for a real terminal. The layout runs before any print, so a
    missing ``viz`` extra raises ``GraphLayoutUnavailable`` with nothing printed.
    """
    graph_style = cast(Style, style)
    topo = payload["topology"]
    nodes, edges = topo["nodes"], topo["edges"]
    palette: Palette = "color" if out.is_terminal else "plain"

    # Lay the graph out before any print: draw_dag raises GraphLayoutUnavailable
    # when grandalf is absent, and a half-drawn view (legend, then a hint) reads
    # as broken. Build everything, then commit it to the console in one pass.
    graph = draw_dag(nodes, edges, style=graph_style, palette=palette)
    legend = dag_legend(nodes, style=graph_style, palette=palette)

    out.print(legend if legend is not None else _role_legend())
    out.print(Text(""))
    # soft_wrap: the DAG is wider than the 88-col default frame; let it overflow
    # rather than wrap (wrapping would shred the box art and split module ids).
    out.print(graph, soft_wrap=True)
    out.print(Text(""))

    source, sink = topo["source"] or "-", topo["sink"] or "-"
    flow = Text(f"source: {source}", style="muted")
    flow.append(f"   sink: {sink}", style="muted")
    out.print(flow)
    out.print(_fanout_note())


def _walks_payload(walk_plan: "WalkPlan") -> list[dict[str, Any]]:
    """The walk census as json-safe rows in counter order, plus ``user_walk``."""
    # Imported here so a bare `dae --help` never pulls daedalus.core.walks and
    # networkx; test_engine_lazy_imports.py enforces the lazy import.
    from daedalus.core.walks import user_walk  # noqa: PLC0415

    return [
        {
            "walk_id": w.walk_id,
            "flight_id": w.flight_id,
            "parent_walk": w.parent_walk,
            "born_at": w.born_at,
            "branch_module": w.branch_module,
            "user_walk": user_walk(w, walk_plan.walks),
        }
        for w in walk_plan.walks
    ]


def visualize_payload_for(graph: "nx.DiGraph", walk_plan: "WalkPlan") -> dict[str, Any]:
    """``visualize_payload`` for a cwd lab graph, with its walk census.

    Same node and edge contract as the exemplar payload, plus ``walks``,
    ``walk_lines`` (the configuration view ``dae lab visualize`` shows) and
    ``token_walk_lines`` (the internal token-set view, for tooling).
    """
    source, sink = _graph_endpoints(graph)
    scoped = _flight_scoped_nodes(graph, lambda node: graph.nodes[node]["role"])
    nodes = [
        {"id": mod, "role": str(role), "layer": layer, "flight_scoped": mod in scoped}
        for mod, role, layer in _layers_of(graph)
    ]
    return {
        "topology": {
            "nodes": nodes,
            "edges": sorted([src, dst] for src, dst in graph.edges()),
            "source": source,
            "sink": sink,
        },
        "walks": _walks_payload(walk_plan),
        "walk_lines": list(walk_plan.config_lines()),
        "token_walk_lines": list(walk_plan.walk_lines()),
    }


def flow_status_payload(record: FlowRecord) -> dict[str, Any]:
    """The on-disk flow record as a json-safe dict for ``dae --json flow status``.

    Each step carries its id, status, wall time and error; ``engine`` and
    ``max_workers`` name the backend and concurrency. The failure cause is not
    merged in here; it rides the envelope ``error`` from :func:`failure_cause`.
    """
    return {
        "flow_id": record.flow_id,
        "lab_name": record.lab_name,
        "status": record.status,
        "created_at": record.created_at,
        "engine": record.engine,
        "max_workers": record.max_workers,
        "steps": [
            {
                "id": step.step_id,
                "status": step.status,
                "duration_s": step.duration_s,
                "started_at": step.started_at,
                "finished_at": step.finished_at,
                "error": step.error,
            }
            for step in record.steps
        ],
        "walks": [
            {
                "walk_id": walk.walk_id,
                "flight_id": walk.flight_id,
                "parent_walk": walk.parent_walk,
                "born_at": walk.born_at,
                "branch_module": walk.branch_module,
                "user_walk": walk.user_walk,
            }
            for walk in record.walks
        ],
    }


def failure_cause(record: FlowRecord) -> dict[str, Any] | None:
    """The envelope ``error`` object for a failed run, or None for a clean one.

    Built from the first failed step, with its message under ``error`` and
    ``reason``, the step-instance id under ``module``, the ``dae.step.*`` code
    under ``code`` when recorded, and the absent package under ``missing_dep``.
    """
    failed = next((step for step in record.steps if step.status == "failed"), None)
    if failed is None or failed.error is None:
        return None
    cause: dict[str, Any] = {
        "error": failed.error,
        "reason": failed.error,
        "module": failed.step_id,
    }
    if failed.error_code is not None:
        cause["code"] = failed.error_code
    missing_dep = _missing_dep(failed.error)
    if missing_dep is not None:
        cause["missing_dep"] = missing_dep
    return cause


def _missing_dep(error: str) -> str | None:
    """The top-level package named by a ``No module named 'X'`` message, or None."""
    marker = "No module named "
    if marker not in error:
        return None
    # Parse the package name out of the "No module named X" message (top-level
    # package, quotes stripped).
    token = error.split(marker, 1)[1].strip().split()[0]
    return token.strip("'\"").split(".")[0] or None


def distill_step_traceback(raw: str) -> str:
    """Reduce a step traceback to its last ``File`` frame and the exception line.

    The full trace stays in ``step-error.log``; this is the part shown inline.
    Empty input yields a short placeholder rather than an exception.
    """
    lines = [line for line in raw.splitlines() if line.strip()]
    if not lines:
        return "(no traceback captured)"
    # The deepest File frame is where the module raised; keep it and what follows.
    frames = [i for i, line in enumerate(lines) if line.lstrip().startswith("File ")]
    if not frames:
        # No frame markers at all (a bare exception line): show the trailing line.
        return lines[-1]
    return "\n".join(lines[frames[-1] :])


def flow_status(record: FlowRecord) -> None:
    """Print the latest flow as a table with one row per step instance.

    Each row carries the ``[walk_J]`` / ``[flight_K]`` label beside the internal
    ``@w<id>`` token. Read-only over the on-disk lineage.
    """
    lab_name = record.lab_name or "(unnamed lab)"
    out.print(report_header(f"{record.flow_id}   {lab_name}   {record.status}"))

    table = _recipe_table()
    # One row per step instance ("<module>@w<walk>"), labeled with the walk or
    # flight name the recipe view uses.
    table.add_column(strings.STEP_INSTANCE)
    table.add_column("status", justify="center")
    table.add_column("time", justify="right", style="muted")
    for i, step in enumerate(record.steps, start=1):
        seconds = "-" if step.duration_s is None else f"{step.duration_s:.2f}s"
        style = "ok" if step.status == "completed" else "muted"
        if step.status == "failed":
            style = "would"
        table.add_row(
            f"{i:02d}",
            Text(""),
            _step_label(step.step_id, record.walks),
            Text(step.status, style=style),
            Text(seconds),
        )
    out.print(table)
    out.print(Text(""))
    _serial_footer(record)
    out.print(Text(strings.STATUS_READ_ONLY, style="muted"))
