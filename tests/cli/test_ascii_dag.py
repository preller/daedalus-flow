"""Unit tests for the draw_dag and dag_legend renderer.

Assertions are structural, not pixel goldens; grandalf's layout is version-sensitive.
"""

from __future__ import annotations

import importlib.util

import pytest
from rich.text import Text

from daedalus.cli.console import ROLE_GLYPH, ROLE_STYLE
from daedalus.cli.render._ascii_dag import dag_legend, draw_dag
from daedalus.core.topology import Role

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("grandalf") is None,
    reason="graph views need the optional viz extra (grandalf)",
)

STYLES = ("full", "num", "rolenum")


def _payload(rows):
    """rows: (id, role, flight_scoped) -> payload node dicts, in order."""
    return [
        {"id": nid, "role": role, "layer": i, "flight_scoped": flight}
        for i, (nid, role, flight) in enumerate(rows)
    ]


# A per-flight band topology (fetch_curve,
# fit_transit) between the emitter and the flight_collector, then a plot fan
# under make_figures converging on a walk_collector.
TOI4409 = (
    _payload(
        [
            ("emit_curves", "emitter", False),
            ("fetch_curve", "transform", True),
            ("fit_transit", "transform", True),
            ("collect_transits", "flight_collector", False),
            ("fit_rv", "transform", False),
            ("make_figures", "transform", False),
            ("plot_phasefold", "transform", False),
            ("plot_ttv", "transform", False),
            ("collect", "walk_collector", False),
        ]
    ),
    [
        ["emit_curves", "fetch_curve"],
        ["fetch_curve", "fit_transit"],
        ["fit_transit", "collect_transits"],
        ["collect_transits", "fit_rv"],
        ["fit_rv", "make_figures"],
        ["make_figures", "plot_phasefold"],
        ["make_figures", "plot_ttv"],
        ["plot_phasefold", "collect"],
        ["plot_ttv", "collect"],
    ],
)

# A structurally different DAG that still exercises all four roles, with a
# two-branch per-flight band.
COMPLEX = (
    _payload(
        [
            ("emit", "emitter", False),
            ("clean", "transform", True),
            ("fit_a", "transform", True),
            ("fit_b", "transform", True),
            ("flight_join", "flight_collector", False),
            ("post", "transform", False),
            ("walk_join", "walk_collector", False),
        ]
    ),
    [
        ["emit", "clean"],
        ["clean", "fit_a"],
        ["clean", "fit_b"],
        ["fit_a", "flight_join"],
        ["fit_b", "flight_join"],
        ["flight_join", "post"],
        ["post", "walk_join"],
    ],
)

TOPOLOGIES = {"toi4409": TOI4409, "complex": COMPLEX}


def _glyphs(nodes):
    return {ROLE_GLYPH[Role(n["role"])] for n in nodes}


def test_draw_dag_returns_rich_text():
    nodes, edges = TOI4409
    assert isinstance(draw_dag(nodes, edges, style="full", palette="plain"), Text)


@pytest.mark.parametrize("topo", TOPOLOGIES)
def test_full_style_shows_every_id_and_role_glyph(topo):
    nodes, edges = TOPOLOGIES[topo]
    plain = draw_dag(nodes, edges, style="full", palette="plain").plain
    present = [n["id"] for n in nodes if n["id"] in plain]
    assert present == [n["id"] for n in nodes]  # count in == labeled out
    for glyph in _glyphs(nodes):
        assert glyph in plain  # E/T/W/F all rendered


@pytest.mark.parametrize("topo", TOPOLOGIES)
@pytest.mark.parametrize("style", ("num", "rolenum"))
def test_numeric_legend_lists_every_id_number_and_glyph(topo, style):
    nodes, edges = TOPOLOGIES[topo]
    legend = dag_legend(nodes, style=style, palette="plain")
    assert legend is not None
    text = legend.plain
    for number, node in enumerate(nodes, start=1):
        assert node["id"] in text
        assert str(number) in text
    for glyph in _glyphs(nodes):
        assert glyph in text


def test_full_style_has_no_legend():
    nodes, _edges = TOI4409
    assert dag_legend(nodes, style="full", palette="plain") is None


@pytest.mark.parametrize("topo", TOPOLOGIES)
def test_full_style_boxes_every_node(topo):
    nodes, edges = TOPOLOGIES[topo]
    plain = draw_dag(nodes, edges, style="full", palette="plain").plain
    # one box per node, four "+" corners each; rails use "*", never "+".
    assert plain.count("+") == 4 * len(nodes)


@pytest.mark.parametrize("style", STYLES)
def test_tilde_count_equals_flight_scoped_nodes(style):
    nodes, edges = TOI4409
    plain = draw_dag(nodes, edges, style=style, palette="plain").plain
    expected = sum(1 for n in nodes if n["flight_scoped"])
    assert expected > 0  # fixture must exercise the tag
    assert plain.count("~") == expected


def test_full_tilde_marks_flight_band_not_plain_nodes():
    nodes, edges = TOI4409
    plain = draw_dag(nodes, edges, style="full", palette="plain").plain
    assert "fetch_curve~" in plain  # in the per-flight band
    assert "emit_curves" in plain  # the emitter is still drawn...
    assert "emit_curves~" not in plain  # ...but is not flight-scoped


@pytest.mark.parametrize("style", STYLES)
def test_color_false_yields_no_style_spans(style):
    nodes, edges = TOI4409
    assert draw_dag(nodes, edges, style=style, palette="plain").spans == []


@pytest.mark.parametrize("style", STYLES)
def test_color_true_styles_each_role_and_dims_edges(style):
    nodes, edges = TOI4409
    used = {
        span.style
        for span in draw_dag(nodes, edges, style=style, palette="color").spans
    }
    assert used  # palette="color" must produce styled spans
    for node in nodes:
        assert ROLE_STYLE[Role(node["role"])] in used  # E/T/W/F all styled
    assert "muted" in used  # box borders + edge rails dimmed


def test_legend_color_false_yields_no_style_spans():
    nodes, _edges = TOI4409
    legend = dag_legend(nodes, style="num", palette="plain")
    assert legend is not None
    assert legend.spans == []


def test_legend_color_true_styles_glyphs():
    nodes, _edges = TOI4409
    legend = dag_legend(nodes, style="num", palette="color")
    assert legend is not None
    used = {span.style for span in legend.spans}
    assert any(s in used for s in ROLE_STYLE.values())


@pytest.mark.parametrize("bad", ["table", "boxed", "", "FULL", "num "])
def test_draw_dag_rejects_unknown_style(bad):
    nodes, edges = TOI4409
    with pytest.raises(ValueError):
        draw_dag(nodes, edges, style=bad, palette="plain")


def test_dag_legend_rejects_unknown_style():
    nodes, _edges = TOI4409
    with pytest.raises(ValueError):
        dag_legend(nodes, style="table", palette="plain")  # type: ignore[arg-type]
