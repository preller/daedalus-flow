"""ASCII canvas, grandalf layout and the boxed DAG renderer for graph views.

``AsciiCanvas`` is an independent character grid with point, line, box and
text; it copies neither dvc's ``dagascii`` nor langchain's ``graph_ascii``.
``_build_layout`` wraps grandalf (the optional ``daedalus-flow[viz]`` extra,
imported lazily) and returns plain dataclasses. ``draw_dag`` and ``dag_legend``
map visualize payload nodes to boxed labels with the glyphs and colors from
``cli.console`` and return Rich ``Text``; ``--json`` never serializes them.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from rich.text import Text

from daedalus.cli.console import ROLE_GLYPH, ROLE_STYLE
from daedalus.core.topology import Role


class AsciiCanvas:
    """A character grid, origin top-left; draws outside the grid are clipped."""

    def __init__(self, width: int, height: int) -> None:
        if width < 1 or height < 1:
            raise ValueError(f"canvas needs positive size, got {width}x{height}")
        self.width = width
        self.height = height
        self._grid: list[list[str]] = [[" "] * width for _ in range(height)]

    def point(self, x: int, y: int, char: str) -> None:
        """Set a single cell, clipping anything outside the grid."""
        if 0 <= x < self.width and 0 <= y < self.height:
            self._grid[y][x] = char

    def line(self, x0: int, y0: int, x1: int, y1: int, char: str) -> None:
        """Stroke a straight run between two cells (integer Bresenham)."""
        dx = abs(x1 - x0)
        dy = -abs(y1 - y0)
        step_x = 1 if x0 < x1 else -1
        step_y = 1 if y0 < y1 else -1
        error = dx + dy
        x, y = x0, y0
        while True:
            self.point(x, y, char)
            if x == x1 and y == y1:
                break
            double = 2 * error
            if double >= dy:
                error += dy
                x += step_x
            if double <= dx:
                error += dx
                y += step_y

    def box(self, x: int, y: int, width: int, height: int) -> None:
        """Draw a rectangle outline with ``+`` corners and ``-`` / ``|`` sides."""
        width = max(width, 2)
        height = max(height, 2)
        right = x + width - 1
        bottom = y + height - 1
        for col in range(x + 1, right):
            self.point(col, y, "-")
            self.point(col, bottom, "-")
        for row in range(y + 1, bottom):
            self.point(x, row, "|")
            self.point(right, row, "|")
        for corner_x, corner_y in ((x, y), (right, y), (x, bottom), (right, bottom)):
            self.point(corner_x, corner_y, "+")

    def text(self, x: int, y: int, value: str) -> None:
        """Write a string left-to-right starting at ``(x, y)``."""
        for offset, char in enumerate(value):
            self.point(x + offset, y, char)

    def draw(self) -> str:
        """Render the grid to a string, trailing blanks stripped per row."""
        return "\n".join("".join(row).rstrip() for row in self._grid)


class VertexViewer:
    """The ``w``, ``h`` and ``xy`` view grandalf reads and writes to place a node."""

    HEIGHT = 3  # top rule, label row, bottom rule

    def __init__(self, label: str) -> None:
        self.label = label
        self.w = len(label) + 2  # the label plus a one-cell border
        self.h = self.HEIGHT
        # Filled in by SugiyamaLayout.draw() as (center_x, top_y).
        self.xy: tuple[float, float] | None = None


class EdgeViewer:
    """Captures the routed polyline grandalf hands back through ``setpath``."""

    def __init__(self) -> None:
        self.pts: list[tuple[float, float]] = []

    def setpath(self, pts: list[tuple[float, float]]) -> None:
        """Store the routed polyline grandalf passes after layout."""
        # SugiyamaLayout.draw() delivers the route through setpath, not by
        # assigning pts.
        self.pts = pts


# What a caller sees when grandalf is not installed. The user-facing outcome text
# lives in the command layer; this is the raised cause it translates.
_MISSING_HINT = (
    "graph views need the optional 'viz' extra (the grandalf layout engine); "
    "install it with: pip install daedalus-flow[viz]"
)


class GraphLayoutUnavailable(RuntimeError):
    """Raised by ``_build_layout`` when the optional grandalf engine is absent."""


@dataclass(frozen=True)
class PlacedVertex:
    """A laid-out node, with its label, top-left cell and box size in grid units."""

    label: str
    left: float
    top: float
    width: int
    height: int


@dataclass(frozen=True)
class LaidOutGraph:
    """A laid-out recipe in one coordinate space; an empty recipe has a zero box."""

    vertices: list[PlacedVertex]
    edges: list[list[tuple[float, float]]]
    minx: float  # the extent the renderer subtracts to project onto a canvas
    miny: float
    maxx: float
    maxy: float


def _placed_vertex(vertex: Any) -> PlacedVertex:
    """Read one grandalf vertex's placed geometry into a plain dataclass."""
    view = vertex.view
    center_x, top = float(view.xy[0]), float(view.xy[1])
    width, height = int(view.w), int(view.h)
    return PlacedVertex(
        label=str(vertex.data),
        left=center_x - width / 2.0,
        top=top,
        width=width,
        height=height,
    )


def _build_graph(
    nodes: Mapping[str, str],
    edges: Sequence[tuple[str, str]],
    vertex_cls: Any,
    edge_cls: Any,
    graph_cls: Any,
) -> Any:
    """Build a grandalf Graph from the recipe, with a view on every vertex/edge."""
    vertices = {nid: vertex_cls(label) for nid, label in nodes.items()}
    for nid, vertex in vertices.items():
        vertex.view = VertexViewer(nodes[nid])
    built_edges = []
    for parent, child in edges:
        edge = edge_cls(vertices[parent], vertices[child])
        edge.view = EdgeViewer()
        built_edges.append(edge)
    return graph_cls(list(vertices.values()), built_edges)


def _lay_out_component(
    component: Any,
    sugiyama_cls: Any,
    route_edge: Any,
    xspace: int,
    yspace: int,
) -> tuple[list[PlacedVertex], list[list[tuple[float, float]]]]:
    """Run Sugiyama on one component; return its placed vertices + edge polylines."""
    sugiyama = sugiyama_cls(component)
    roots = [v for v in component.sV if len(v.e_in()) == 0]
    sugiyama.init_all(roots=roots, optimize=True)
    sugiyama.xspace = xspace
    sugiyama.yspace = yspace
    sugiyama.route_edge = route_edge
    sugiyama.draw()
    placed = [_placed_vertex(v) for v in component.sV]
    polylines = [
        [(float(px), float(py)) for px, py in edge.view.pts] for edge in component.sE
    ]
    return placed, polylines


def _bounds(
    vertices: list[PlacedVertex], polylines: list[list[tuple[float, float]]]
) -> tuple[float, float, float, float]:
    """The (minx, miny, maxx, maxy) extent of everything; zeroes when empty."""
    xs: list[float] = []
    ys: list[float] = []
    for pv in vertices:
        xs += [pv.left, pv.left + pv.width]
        ys += [pv.top, pv.top + pv.height]
    for line in polylines:
        xs += [px for px, _ in line]
        ys += [py for _, py in line]
    if not xs:
        return 0.0, 0.0, 0.0, 0.0
    return min(xs), min(ys), max(xs), max(ys)


def _build_layout(
    nodes: Mapping[str, str],
    edges: Sequence[tuple[str, str]],
    *,
    xspace: int = 1,
    yspace: int = 1,
) -> LaidOutGraph:
    """Lay out ``nodes`` (id to label) and ``edges`` with grandalf's Sugiyama layout."""
    try:
        from grandalf.graphs import (  # noqa: PLC0415 (lazy: viz extra)
            Edge,
            Graph,
            Vertex,
        )
        from grandalf.layouts import SugiyamaLayout  # noqa: PLC0415 (lazy: viz extra)
        from grandalf.routing import (  # noqa: PLC0415 (lazy: viz extra)
            route_with_lines,
        )
    except ImportError as exc:
        raise GraphLayoutUnavailable(_MISSING_HINT) from exc

    graph = _build_graph(nodes, edges, Vertex, Edge, Graph)
    placed: list[PlacedVertex] = []
    polylines: list[list[tuple[float, float]]] = []
    # daedalus recipes are connected (single source / sink), so graph.C is one
    # component; the loop stays correct if that ever relaxes.
    for component in graph.C:
        component_vertices, component_edges = _lay_out_component(
            component, SugiyamaLayout, route_with_lines, xspace, yspace
        )
        placed += component_vertices
        polylines += component_edges

    minx, miny, maxx, maxy = _bounds(placed, polylines)
    return LaidOutGraph(placed, polylines, minx, miny, maxx, maxy)


# The three graph label styles. ``table`` is not here: the command maps that to
# the existing Rich topology table, never to this function.
_LABEL_STYLES = ("full", "num", "rolenum")
Style = Literal["full", "num", "rolenum"]

# A string mode rather than a bool, matching ``_build_layout``'s ``router``: the
# renderer either tints role cells / dims chrome (``"color"``) or stays ANSI-free
# (``"plain"``, e.g. when piped).
Palette = Literal["plain", "color"]

# Layout spacing per style. ``full`` carries the whole module id, so it stays
# tight; the short numeric labels get roomy spacing so the rails between boxes
# stay legible (the spike finding).
_SPACING = {"full": (1, 1), "num": (2, 2), "rolenum": (2, 2)}

_EDGE_CHAR = "*"
_FLIGHT_TAG = "~"  # trails a per-flight-band module's label
_DIM_STYLE = "muted"  # box borders + edge rails; a registered DAE_THEME key


def _require_style(style: str) -> None:
    """Reject any style this renderer does not draw (``table`` included)."""
    if style not in _LABEL_STYLES:
        raise ValueError(
            f"unknown graph style {style!r}; expected one of {list(_LABEL_STYLES)}"
        )


def _node_label(node: Mapping[str, Any], style: str, number: int) -> str:
    """The box text for one node under ``style``, with the flight ``~`` tag."""
    glyph = ROLE_GLYPH[Role(node["role"])]
    if style == "full":
        label = f"{glyph} {node['id']}"
    elif style == "num":
        label = str(number)
    else:  # rolenum
        label = f"{glyph}{number}"
    if node["flight_scoped"]:
        label += _FLIGHT_TAG
    return label


def draw_dag(
    nodes: Sequence[Mapping[str, Any]],
    edges: Sequence[Sequence[str]],
    *,
    style: Style,
    palette: Palette,
) -> Text:
    """Render a visualize payload as a boxed ASCII DAG in a Rich ``Text``.

    ``nodes`` are in payload order (their 1-based position is the numeric label).
    ``style`` boxes glyph and id (full), the number (num) or both (rolenum);
    ``palette`` "color" tints labels by role and dims rails. Needs the viz extra.
    """
    _require_style(style)
    if not nodes:
        return Text()

    labels = {
        node["id"]: _node_label(node, style, number)
        for number, node in enumerate(nodes, start=1)
    }
    label_style = {labels[node["id"]]: ROLE_STYLE[Role(node["role"])] for node in nodes}
    xspace, yspace = _SPACING[style]
    layout = _build_layout(
        labels, [(src, dst) for src, dst in edges], xspace=xspace, yspace=yspace
    )
    return _project(layout, label_style, palette)


def _project(
    layout: LaidOutGraph, label_style: Mapping[str, str], palette: Palette
) -> Text:
    """Stamp a laid-out graph onto a canvas and convert it to a Rich ``Text``."""
    minx, miny = layout.minx, layout.miny
    width = math.ceil(layout.maxx - minx) + 2
    height = math.ceil(layout.maxy - miny) + 2
    canvas = AsciiCanvas(width, height)

    # Edges first, so a box border overwrites the rail cell where they meet.
    for polyline in layout.edges:
        for (x0, y0), (x1, y1) in zip(polyline, polyline[1:], strict=False):
            canvas.line(
                round(x0 - minx),
                round(y0 - miny),
                round(x1 - minx),
                round(y1 - miny),
                _EDGE_CHAR,
            )

    # (x, y, length, style) per label run, applied as an overlay onto the grid.
    label_runs: list[tuple[int, int, int, str]] = []
    for vertex in layout.vertices:
        left = round(vertex.left - minx)
        top = round(vertex.top - miny)
        canvas.box(left, top, vertex.width, vertex.height)
        canvas.text(left + 1, top + 1, vertex.label)
        run = (left + 1, top + 1, len(vertex.label), label_style[vertex.label])
        label_runs.append(run)

    return _grid_to_text(canvas, label_runs, palette)


def _grid_to_text(
    canvas: AsciiCanvas,
    label_runs: Sequence[tuple[int, int, int, str]],
    palette: Palette,
) -> Text:
    """Build a Rich ``Text`` from the drawn canvas and the label-run overlay."""
    colored = palette == "color"
    rendered = canvas.draw().split("\n")
    # Every drawn (non-space) cell is dim; the label runs override their cells.
    styles: list[list[str | None]] = [
        [_DIM_STYLE if char != " " else None for char in line] for line in rendered
    ]
    for x, y, length, style in label_runs:
        if 0 <= y < len(styles):
            row = styles[y]
            for col in range(x, min(x + length, len(row))):
                row[col] = style

    text = Text()
    last = len(rendered) - 1
    for y, line in enumerate(rendered):
        for col, char in enumerate(line):
            text.append(char, style=styles[y][col] if colored else None)
        if y != last:
            text.append("\n")
    return text


def dag_legend(
    nodes: Sequence[Mapping[str, Any]], *, style: Style, palette: Palette
) -> Text | None:
    """The id legend for the numeric styles, or None for ``full``.

    ``num`` keys each row by its number and ``rolenum`` by glyph and number. Both
    spell out the role glyph and module id. A closing line explains the ``~``
    tag when any module runs inside the per-flight band.
    """
    _require_style(style)
    if style == "full":
        return None

    colored = palette == "color"
    text = Text()
    any_flight = False
    last = len(nodes) - 1
    for index, node in enumerate(nodes):
        number = index + 1
        glyph = ROLE_GLYPH[Role(node["role"])]
        role_style = ROLE_STYLE[Role(node["role"])] if colored else None
        if style == "num":
            text.append(f"{number} = ")
            text.append(glyph, style=role_style)
            text.append(f" {node['id']}")
        else:  # rolenum, where the key already carries the glyph
            text.append(glyph, style=role_style)
            text.append(f"{number} = {node['id']}")
        if node["flight_scoped"]:
            text.append(_FLIGHT_TAG, style=_DIM_STYLE if colored else None)
            any_flight = True
        if index != last:
            text.append("\n")
    if any_flight:
        text.append("\n")
        text.append(
            f"{_FLIGHT_TAG} = runs inside the per-flight band",
            style=_DIM_STYLE if colored else None,
        )
    return text
