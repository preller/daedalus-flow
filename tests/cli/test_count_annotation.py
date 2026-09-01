"""A static count that diverges from the run count carries an explanation line.

The tests assert the explanation, never a count the render code already prints.
"""

from __future__ import annotations

from contextlib import chdir
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tests._helpers import _copy_example

from ._cli_contract import _human_stdout

pytestmark = pytest.mark.integration  # integration tier, CLI command chains


def _annotation_present(text: str) -> bool:
    """True when the text names ``dae lab run`` plus fan, expand or input row."""
    low = text.lower()
    return "dae lab run" in low and (
        "fan" in low or "expand" in low or "input row" in low
    )


def test_dry_run_explains_fanout_to_runtime_count(tmp_path: Path) -> None:
    """``lab run --dry-run`` annotates that the recipe count expands at run time."""
    # ensemble is the packaged fan-out exemplar: 3 modules in the recipe, and an
    # emitter that fans the input rows into per-target flights. The run expands
    # to more step instances than the recipe lists.
    lab = _copy_example("ensemble", tmp_path)
    with chdir(lab):
        text = _human_stdout(CliRunner(), ["lab", "run", "--dry-run"])
    assert _annotation_present(text), (
        "dry-run must explain that fanned modules expand by input rows at run "
        f"time; got:\n{text}"
    )


def test_visualize_explains_fanout_to_runtime_count(tmp_path: Path) -> None:
    """``lab visualize`` annotates that the static recipe expands at run time."""
    lab = _copy_example("ensemble", tmp_path)
    with chdir(lab):
        text = _human_stdout(CliRunner(), ["lab", "visualize"])
    assert _annotation_present(text), (
        "visualize must explain that the static recipe fans out by input rows "
        f"at run time; got:\n{text}"
    )
