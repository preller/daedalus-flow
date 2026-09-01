"""Shell completion is enabled but kept out of the locked surface snapshot.

The completion options are framework noise, like ``--help``; the golden omits them.
"""

from __future__ import annotations

import re

from typer.testing import CliRunner

from daedalus.cli.app import app
from tests.cli.test_cli_surface import _render_surface

OK_EXIT = 0

# A color-capable runner styles the option name, and the style codes split the
# literal `--install-completion` token, so ANSI is stripped before the check.
_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def test_completion_is_offered_in_root_help() -> None:
    """``dae --help`` advertises the completion installer (completion is enabled)."""
    runner = CliRunner()
    result = runner.invoke(app, ["--help"], prog_name="dae")
    assert result.exit_code == OK_EXIT, result.output
    plain = _ANSI.sub("", result.output)
    assert "--install-completion" in plain, result.output
    assert "--show-completion" in plain, result.output


def test_completion_options_are_excluded_from_the_surface_snapshot() -> None:
    """The locked surface contract never carries completion framework noise."""
    surface = _render_surface()
    assert "install-completion" not in surface, surface
    assert "show-completion" not in surface, surface
