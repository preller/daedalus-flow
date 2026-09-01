"""Unit tests for the ASCII canvas in cli/render/_ascii_dag.py.

The canvas is a local implementation, so it gets exact-output tests; no grandalf here.
"""

from __future__ import annotations

import pytest

from daedalus.cli.render._ascii_dag import (
    AsciiCanvas,
    EdgeViewer,
    VertexViewer,
)


def test_empty_canvas_draws_blank_rows() -> None:
    # rstrip per row collapses an all-space grid to empty lines.
    assert AsciiCanvas(4, 2).draw() == "\n"


def test_point_sets_one_cell() -> None:
    canvas = AsciiCanvas(3, 2)
    canvas.point(1, 0, "x")
    assert canvas.draw() == " x\n"


def test_point_out_of_bounds_is_a_silent_no_op() -> None:
    canvas = AsciiCanvas(2, 2)
    # Negative and past-edge coordinates must neither raise nor draw.
    canvas.point(-1, 0, "x")
    canvas.point(0, 5, "x")
    canvas.point(2, 0, "x")
    assert canvas.draw() == "\n"


def test_horizontal_line_fills_the_row() -> None:
    canvas = AsciiCanvas(4, 1)
    canvas.line(0, 0, 3, 0, "*")
    assert canvas.draw() == "****"


def test_vertical_line_fills_the_column() -> None:
    canvas = AsciiCanvas(2, 3)
    canvas.line(1, 0, 1, 2, "|")
    assert canvas.draw() == " |\n |\n |"


def test_diagonal_line_steps_one_per_cell() -> None:
    canvas = AsciiCanvas(3, 3)
    canvas.line(0, 0, 2, 2, "*")
    assert canvas.draw() == "*\n *\n  *"


def test_line_is_drawn_regardless_of_endpoint_order() -> None:
    forward = AsciiCanvas(3, 3)
    forward.line(0, 0, 2, 2, "*")
    backward = AsciiCanvas(3, 3)
    backward.line(2, 2, 0, 0, "*")
    assert forward.draw() == backward.draw()


def test_box_draws_corners_and_sides() -> None:
    canvas = AsciiCanvas(4, 3)
    canvas.box(0, 0, 4, 3)
    assert canvas.draw() == "+--+\n|  |\n+--+"


def test_text_writes_left_to_right() -> None:
    canvas = AsciiCanvas(5, 1)
    canvas.text(1, 0, "hi")
    assert canvas.draw() == " hi"


def test_text_clips_past_the_right_edge() -> None:
    canvas = AsciiCanvas(3, 1)
    canvas.text(2, 0, "abc")  # only the first char fits
    assert canvas.draw() == "  a"


def test_boxed_label_composes() -> None:
    # A node the way the renderer builds it: a box with its label inside.
    canvas = AsciiCanvas(5, 3)
    canvas.box(0, 0, 5, 3)
    canvas.text(1, 1, "fit")
    assert canvas.draw() == "+---+\n|fit|\n+---+"


def test_canvas_rejects_non_positive_size() -> None:
    with pytest.raises(ValueError, match="positive size"):
        AsciiCanvas(0, 3)


def test_vertex_viewer_sizes_a_boxed_label() -> None:
    # width = label + one border cell each side; height = 3 (top, label, bottom).
    view = VertexViewer("fetch_curve")
    assert view.w == len("fetch_curve") + 2
    assert view.h == 3
    assert view.xy is None  # grandalf fills this in during layout


def test_edge_viewer_starts_with_no_points() -> None:
    assert EdgeViewer().pts == []
