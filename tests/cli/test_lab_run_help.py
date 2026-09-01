"""``dae lab run --help`` makes no false claim about the engine.

The engine is serial only at the default max_workers; branching labs run.
"""

from __future__ import annotations

import re

from typer.testing import CliRunner

from daedalus.cli.app import app


def _run_help() -> str:
    """``dae lab run --help`` text with whitespace collapsed (exit 0)."""
    runner = CliRunner()
    result = runner.invoke(app, ["lab", "run", "--help"], prog_name="dae")
    assert result.exit_code == 0, result.output
    return re.sub(r"\s+", " ", result.output)


def test_lab_run_help_drops_the_false_serial_engine_claim() -> None:
    """Serial is only the default; the scheduler parallelizes at max_workers > 1."""
    help_text = _run_help()
    assert "serial local engine" not in help_text, help_text


def test_lab_run_help_drops_the_false_linear_only_claim() -> None:
    """A branching role-valid DAG runs, as the complex journey test shows."""
    help_text = _run_help()
    assert "runs only linear labs" not in help_text, help_text
    assert "only linear labs" not in help_text, help_text
