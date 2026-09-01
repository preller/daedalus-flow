"""The graph definition for the canonical exo-survey exemplar, as data.

Nodes, edges and the directory conventions live here; source, sink and
topological order are derived. ``render.py`` draws the recipe from here and
``strings.py`` reuses the identity constants. No filesystem access::

    emit_targets [E] -> fetch_data [T] -> { fit_nested [T], fit_mcmc [T] }
                -> compare_methods [W] -> summarize_population [F]
"""

from graphlib import TopologicalSorter

# The public role vocabulary, re-exported as topology.Role; the "as" alias
# makes the re-export explicit under mypy's no_implicit_reexport.
from daedalus.flow import Role as Role  # noqa: PLC0414

# Exemplar identity, shared by render + strings so the story stays one story.
LAB = "exo-survey"
FLOW_ID = "flow_20260101T000000Z"

# The dot dir is internal run-once staging, one ``.daedalus/<token>/<NN>_<module>/``
# per unique instance, cleared at the start of every run and swept by
# ``dae lab clean``. The non-dot root holds the user-facing artifacts.
INTERNAL_DIR = ".daedalus"
OUTPUT_ROOT = "dae-outputs"
# The per-flow discoverability copy of the final module's outputs, a sibling of
# the step dirs inside each flow dir; the nested run tree writes ``final/`` instead.
# TODO: remove once the last reader of ``output/`` is gone.
FLOW_OUTPUT_DIR = "output"

# Reserved dir names for the nested run tree, Flow -> Flight -> Walk -> Step:
# ``flights/flight_K/walks/walk_J/<NN>_<step>/`` plus a per-flight and a
# flow-level ``final/``. The internal ``w<id>`` token never reaches the disk.
FLIGHTS_DIR = "flights"
WALKS_DIR = "walks"
FLIGHT_DIR_PREFIX = "flight_"
WALK_DIR_PREFIX = "walk_"
FINAL_DIR = "final"

# The recipe as data: (module id, role) in declaration / topological order.
NODES: list[tuple[str, Role]] = [
    ("emit_targets", Role.EMITTER),
    ("fetch_data", Role.TRANSFORM),
    ("fit_nested", Role.TRANSFORM),
    ("fit_mcmc", Role.TRANSFORM),
    ("compare_methods", Role.WALK_COLLECTOR),
    ("summarize_population", Role.FLIGHT_COLLECTOR),
]

# Directed edges (src feeds dst). emit_targets is the single source;
# summarize_population the single sink.
EDGES: list[tuple[str, str]] = [
    ("emit_targets", "fetch_data"),
    ("fetch_data", "fit_nested"),
    ("fetch_data", "fit_mcmc"),
    ("fit_nested", "compare_methods"),
    ("fit_mcmc", "compare_methods"),
    ("compare_methods", "summarize_population"),
]

STEP_COUNT = len(NODES)

_ROLE_BY_NAME = dict(NODES)


def role_of(name: str) -> Role:
    """Role for a module basename by string lookup; unknown modules are transforms."""
    return _ROLE_BY_NAME.get(name, Role.TRANSFORM)


def feeds_into(node: str) -> list[str]:
    """Downstream targets of a node, in edge order."""
    return [dst for src, dst in EDGES if src == node]


def _has_incoming(node: str) -> bool:
    return any(dst == node for _, dst in EDGES)


def _has_outgoing(node: str) -> bool:
    return any(src == node for src, _ in EDGES)


def sources() -> list[str]:
    """Nodes with no incoming edge (structurally derived)."""
    return [n for n, _ in NODES if not _has_incoming(n)]


def sinks() -> list[str]:
    """Nodes with no outgoing edge (structurally derived)."""
    return [n for n, _ in NODES if not _has_outgoing(n)]


def source() -> str:
    """The single start emitter (v1 rule: exactly one source)."""
    found = sources()
    # An invariant of the static recipe data, not a check on user input.
    assert len(found) == 1, f"expected exactly one source, got {found}"  # noqa: S101
    return found[0]


def sink() -> str:
    """The single terminal flight_collector (v1 rule: exactly one sink)."""
    found = sinks()
    assert len(found) == 1, f"expected exactly one sink, got {found}"  # noqa: S101
    return found[0]


def ranked() -> list[tuple[str, Role]]:
    """NODES in topological order, validating the recipe is a DAG.

    ``static_order`` raises :class:`graphlib.CycleError` if the recipe is not
    acyclic. Initial-ready nodes, and children as they free up, come out in
    ``NODES`` declaration order, so the rendered order tracks the recipe.
    """
    sorter = TopologicalSorter({n: set() for n, _ in NODES})
    for src, dst in EDGES:
        sorter.add(dst, src)
    return [(n, _ROLE_BY_NAME[n]) for n in sorter.static_order()]


def steps_phrase(n: int) -> str:
    """``1 step`` / ``N steps``."""
    return f"{n} step{'s' if n != 1 else ''}"


def flight_dir(flow: str, flight: int) -> str:
    """``.../flows/<flow>/flights/flight_K/``, a per-flight scope dir.

    K is the runtime 1-based flight index. A string builder over the constants
    above; the engine path build consumes it.
    """
    return f"{OUTPUT_ROOT}/flows/{flow}/{FLIGHTS_DIR}/{FLIGHT_DIR_PREFIX}{flight}/"


def walk_dir(flow: str, flight: int, walk: int) -> str:
    """``.../flights/flight_K/walks/walk_J/``, a per-walk method dir.

    J is the user-facing 1-based walk index, reset per flight. A string builder
    over the constants above; the engine path build consumes it.
    """
    return f"{flight_dir(flow, flight)}{WALKS_DIR}/{WALK_DIR_PREFIX}{walk}/"


def flight_final_dir(flow: str, flight: int) -> str:
    """``.../flights/flight_K/final/`` - per-flight ``final/`` (walk-collector tail)."""
    return f"{flight_dir(flow, flight)}{FINAL_DIR}/"


def flow_final_dir(flow: str) -> str:
    """``.../flows/<flow>/final/`` - the flow-level ``final/`` (the sink result).

    Replaces the deprecated ``output/`` dir at the flow level; the engine
    cutover stops writing ``output/`` and writes this instead.
    """
    return f"{OUTPUT_ROOT}/flows/{flow}/{FINAL_DIR}/"


def try_path(mod: str) -> str:
    """``dae-outputs/try/<mod>/`` - the isolated ``module try`` sandbox (echoed)."""
    return f"{OUTPUT_ROOT}/try/{mod}/"
