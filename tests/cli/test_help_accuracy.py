"""Help text and success copy say what the commands do.

Assertions are whitespace-normalized, so they pin wording, not the wrap column.
"""

from __future__ import annotations

import re

from typer.testing import CliRunner

from daedalus.cli import strings
from daedalus.cli.app import app

# Every command whose docstring surfaces as ``--help``.
_HELP_COMMANDS: list[list[str]] = [
    ["lab", "init"],
    ["lab", "validate"],
    ["lab", "visualize"],
    ["lab", "run"],
    ["lab", "clean"],
    ["module", "create"],
    ["module", "validate"],
    ["module", "try"],
    ["module", "convert"],
    ["flow", "status"],
    ["flow", "resume"],
    ["example"],
]


def _help(args: list[str]) -> str:
    """Return ``dae <args> --help`` with whitespace collapsed (exit 0)."""
    runner = CliRunner()
    result = runner.invoke(app, [*args, "--help"], prog_name="dae")
    assert result.exit_code == 0, result.output
    return re.sub(r"\s+", " ", result.output)


# reStructuredText double-backtick leak


def test_no_command_help_leaks_rst_double_backticks() -> None:
    """No ``--help`` body contains a literal reStructuredText double-backtick."""
    for args in _HELP_COMMANDS:
        help_text = _help(args)
        assert "``" not in help_text, (args, help_text)


# outcome code prefix in help text


def test_lab_validate_help_names_the_real_outcome_code() -> None:
    """The help names the emitted code with its ``dae.`` prefix."""
    help_text = _help(["lab", "validate"])
    assert "dae.lab.validate.ok" in help_text, help_text


# emitter cardinality in help text


def test_lab_validate_help_does_not_claim_one_emitter() -> None:
    """A single-target lab has no emitter and validates, so an emitter is optional."""
    help_text = _help(["lab", "validate"])
    assert "one emitter" not in help_text, help_text


def test_lab_validate_help_states_the_real_structural_rule() -> None:
    """The help states the rule as no dangling deps and no cycles."""
    help_text = _help(["lab", "validate"])
    assert "dangling" in help_text, help_text
    assert "cycle" in help_text or "cycles" in help_text, help_text


# structure-only copy on module validate


def test_module_validate_copy_marks_the_check_as_structure_only() -> None:
    """The module-validate success copy says the check does not run the code."""
    rows = strings.module_validate_rows("modules/fit_nested")
    joined = " ".join(f"{field} {value}" for field, value in rows).lower()
    assert "structure only" in joined, rows
    assert "does not run" in joined, rows


def test_module_validate_markers_row_tracks_the_scan_count() -> None:
    """The markers row reflects the scanned count, never a canned "none"."""
    clean = dict(strings.module_validate_rows("modules/fit_nested"))
    stubbed = dict(strings.module_validate_rows("modules/fit_nested", 1))
    assert clean["markers"] == "none unresolved", clean
    assert stubbed["markers"] == "1 unresolved (NotImplementedError)", stubbed


# -h as an alias of --help


def test_short_help_flag_works_at_the_root() -> None:
    """``dae -h`` is the same help as ``dae --help`` (exit 0, shows Usage)."""
    runner = CliRunner()
    result = runner.invoke(app, ["-h"], prog_name="dae")
    assert result.exit_code == 0, result.output
    assert "Usage" in result.output, result.output


def test_short_help_flag_propagates_to_groups_and_leaves() -> None:
    """``-h`` is wired once on the root; Click propagates it down the context tree."""
    runner = CliRunner()
    for args in (["lab", "-h"], ["lab", "run", "-h"]):
        result = runner.invoke(app, args, prog_name="dae")
        assert result.exit_code == 0, (args, result.output)
        assert "Usage" in result.output, (args, result.output)
