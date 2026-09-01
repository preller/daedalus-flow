"""Presentation contracts over ``cli/render/_topology.py`` and ``cli/strings.py``.

The fan-out fixtures are ``diamond_join`` (branch walks) and ``ensemble`` (flights).
"""

from __future__ import annotations

import re
from contextlib import chdir
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tests._helpers import _copy_example
from tests.cli._cli_contract import (
    _copy_fixture_lab,
    _human_stdout,
    _reset_json_state,
)

pytestmark = pytest.mark.integration

__all__ = ["_reset_json_state"]


def _run_human(lab: Path, *argv: str) -> str:
    """Render ``argv`` on the human path with cwd inside ``lab``."""
    with chdir(lab):
        return _human_stdout(CliRunner(), list(argv))


# the dry-run module-dir column shows the lab-relative leaf


def test_dry_run_shows_lab_relative_module_leaf(tmp_path: Path) -> None:
    """The dry-run plan shows ``modules/<name>`` for each module, never truncated."""
    lab = _copy_example("ensemble", tmp_path)
    text = _run_human(lab, "lab", "run", "--dry-run")
    for module_id in ("emit", "analyze", "collect"):
        assert f"modules/{module_id}" in text, (
            f"dry-run must show the lab-relative leaf modules/{module_id}; got:\n{text}"
        )


def test_dry_run_module_leaf_survives_narrow_terminal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A lab-relative path keeps the leaf visible where an absolute path lost it."""
    monkeypatch.setenv("DAE_WIDTH", "60")
    lab = _copy_example("ensemble", tmp_path)
    text = _run_human(lab, "lab", "run", "--dry-run")
    for module_id in ("emit", "analyze", "collect"):
        assert f"modules/{module_id}" in text, (
            f"narrow-width dry-run lost the modules/{module_id} leaf; got:\n{text}"
        )
    # The absolute lab path must not fill the column.
    assert str(lab) not in text, (
        "dry-run must print lab-relative module paths, not the absolute lab path"
    )


# lineage on one unwrapped line; the result path is printed


def _deep_lab(tmp_path: Path) -> Path:
    """A linear_smoke copy under a deep path, for a long lineage line."""
    deep = tmp_path / "a_rather_long_directory_name" / "and_another_deep_segment"
    deep.mkdir(parents=True)
    return _copy_fixture_lab("linear_smoke", deep)


def test_lineage_path_is_one_unwrapped_line(tmp_path: Path) -> None:
    """A deep lab path exceeds the 88-col frame and still prints on one line."""
    lab = _deep_lab(tmp_path)
    text = _run_human(lab, "lab", "run")
    flow_dir = lab / "dae-outputs" / "flows"
    lineage_lines = [ln for ln in text.splitlines() if "lineage:" in ln]
    assert lineage_lines, f"no lineage line in run output; got:\n{text}"
    line = lineage_lines[0]
    assert str(flow_dir) in line, (
        f"the lineage path must be whole on one line, not wrapped; got line:\n{line}"
    )


def test_run_names_canonical_result_path(tmp_path: Path) -> None:
    """The engine writes final/, not the stale output/ the old gate pointed at."""
    lab = _copy_fixture_lab("linear_smoke", tmp_path)
    text = _run_human(lab, "lab", "run")
    # The flow's final/ dir is the canonical result (run_report.json lives there).
    final_dirs = list((lab / "dae-outputs" / "flows").glob("*/final"))
    assert final_dirs, "the run should have written a flow final/ dir"
    assert str(final_dirs[0]) in text, (
        f"run output must name the canonical result path {final_dirs[0]}; got:\n{text}"
    )


# lab run is compact; flow status keeps the full per-step table


def test_run_is_compact_and_differs_from_status(tmp_path: Path) -> None:
    """run prints a compact summary; status keeps the full per-step table."""
    lab = _copy_example("ensemble", tmp_path)
    run_text = _run_human(lab, "lab", "run")
    status_text = _run_human(lab, "flow", "status")

    assert run_text.strip() != status_text.strip(), (
        "lab run must not be byte-identical to flow status"
    )
    # status prints one row per step instance (6 for ensemble); run, being a
    # compact summary, prints strictly fewer lines.
    assert len(run_text.splitlines()) < len(status_text.splitlines()), (
        f"lab run must be shorter than flow status; run:\n{run_text}\n"
        f"status:\n{status_text}"
    )
    # The full per-step table belongs to status: every fanned analyze instance is
    # listed there.
    assert status_text.count("analyze") >= 4, (
        f"flow status must keep the full per-step table; got:\n{status_text}"
    )


# visualize table rule widths agree

_RULE_RE = re.compile(r"^[─━\-]{3,}\s*$")


def _rule_widths(text: str) -> list[int]:
    """The lengths of every horizontal-rule line (trailing spaces stripped)."""
    return [len(ln.rstrip()) for ln in text.splitlines() if _RULE_RE.match(ln)]


def test_visualize_rule_widths_agree(tmp_path: Path) -> None:
    """The header underline and the table separator share one width."""
    lab = _copy_example("ensemble", tmp_path)
    text = _run_human(lab, "lab", "visualize")
    widths = _rule_widths(text)
    assert len(widths) >= 2, f"expected at least two rule lines; got:\n{text}"
    # The header underline and the table's own separator must be equal, not the
    # 88-vs-content mismatch.
    assert len(set(widths)) == 1, (
        f"visualize rule widths disagree: {widths}; got:\n{text}"
    )


# a glyph legend for {} () [] appears under the walk lines


def test_visualize_prints_glyph_legend_for_walk_lines(tmp_path: Path) -> None:
    """The node table's E/T/W/F legend gets a sibling for the walk-line glyphs."""
    lab = _copy_example("ensemble", tmp_path)
    text = _run_human(lab, "lab", "visualize")
    low = text.lower()
    # The three glyph forms must each be explained in a legend line.
    assert "{}" in text and "()" in text and "[]" in text, (
        f"the glyph legend must show all three glyph forms; got:\n{text}"
    )
    assert "branch" in low, f"legend must name the branch glyph; got:\n{text}"
    assert "walk-collector" in low or "walk collector" in low, (
        f"legend must name the walk-collector glyph; got:\n{text}"
    )
    assert "flight-collector" in low or "flight collector" in low, (
        f"legend must name the flight-collector glyph; got:\n{text}"
    )


# module (recipe) and step instance (run) used consistently


def test_visualize_counts_modules_run_counts_step_instances(tmp_path: Path) -> None:
    """Visualize counts ``modules``; run/status count ``step instances``."""
    lab = _copy_example("ensemble", tmp_path)
    visualize = _run_human(lab, "lab", "visualize")
    assert "module" in visualize.lower(), (
        f"visualize must describe the static recipe as modules; got:\n{visualize}"
    )

    run_text = _run_human(lab, "lab", "run")
    status_text = _run_human(lab, "flow", "status")
    for label, text in (("run", run_text), ("status", status_text)):
        assert "step instance" in text.lower(), (
            f"{label} must call the runtime units 'step instance'; got:\n{text}"
        )


# fanned run and status steps carry the walk_J or flight_K label


def test_compact_run_does_not_expose_bare_internal_tokens(tmp_path: Path) -> None:
    """The walk_J vocabulary lives in status; the compact run hides module@wN ids."""
    lab = _copy_fixture_lab("diamond_join", tmp_path)
    text = _run_human(lab, "lab", "run")
    assert "@w2" not in text and "@w3" not in text, (
        f"compact run must not surface the bare internal @w tokens; got:\n{text}"
    )


def test_status_labels_branch_walks_with_user_walk(tmp_path: Path) -> None:
    """``flow status`` over a branching lab labels fanned steps with ``walk_J``."""
    lab = _copy_fixture_lab("diamond_join", tmp_path)
    _run_human(lab, "lab", "run")
    text = _run_human(lab, "flow", "status")
    assert "walk_1" in text and "walk_2" in text, (
        f"status must label the branch walks with their user-facing walk_J; "
        f"got:\n{text}"
    )


def test_status_labels_flight_walks_with_flight_id(tmp_path: Path) -> None:
    """ensemble fans into four flight walks, labelled flight_1..flight_4 in status."""
    lab = _copy_example("ensemble", tmp_path)
    _run_human(lab, "lab", "run")
    text = _run_human(lab, "flow", "status")
    for flight in ("flight_1", "flight_2", "flight_3", "flight_4"):
        assert flight in text, (
            f"status must label each fanned step with its flight ({flight}); "
            f"got:\n{text}"
        )
