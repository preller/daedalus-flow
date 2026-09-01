"""``--version`` and ``-V`` are eager meta-flags outside the outcome-code contract.

The flag echoes ``daedalus.__version__`` from the installed distribution metadata.
"""

from __future__ import annotations

from typer.testing import CliRunner

from daedalus import __version__
from daedalus.cli.app import app

OK_EXIT = 0


def _invoke(flag: str) -> tuple[int, str]:
    """Return ``(exit_code, stripped stdout)`` for ``dae <flag>``."""
    runner = CliRunner()
    result = runner.invoke(app, [flag], prog_name="dae")
    return result.exit_code, result.output.strip()


def test_long_version_prints_the_metadata_version_and_exits_zero() -> None:
    """``dae --version`` is exit 0 and echoes ``__version__`` verbatim."""
    code, out = _invoke("--version")
    assert code == OK_EXIT, out
    assert out == f"dae {__version__}", out


def test_short_version_flag_matches_the_long_form() -> None:
    """``-V`` is wired as the short alias and prints the same line."""
    code, out = _invoke("-V")
    assert code == OK_EXIT, out
    assert out == f"dae {__version__}", out


def test_version_emits_no_outcome_code_envelope() -> None:
    """``--version`` fires before the root callback sets the json state."""
    runner = CliRunner()
    result = runner.invoke(app, ["--json", "--version"], prog_name="dae")
    assert result.exit_code == OK_EXIT, result.output
    assert result.output.strip() == f"dae {__version__}", result.output
    assert "dae.version" not in result.output, result.output
    assert "{" not in result.output, result.output  # no JSON object leaked
