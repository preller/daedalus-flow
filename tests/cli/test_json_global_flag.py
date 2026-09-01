"""``--json`` is one global flag, accepted before or after the command noun.

Both forms flip the same ``state["json"]`` and emit the identical envelope.
"""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from daedalus.cli.app import app
from tests.cli._cli_contract import OK_EXIT, _isolated_cwd, _reset_json_state

pytestmark = pytest.mark.integration  # integration tier, CLI surface contract

# Re-export the autouse fixture so ruff does not flag the import as unused; pytest
# resolves it by name in this module's namespace.
__all__ = ["_reset_json_state"]


@pytest.mark.parametrize(
    ("argv", "code"),
    [
        (["lab", "visualize", "--json"], "dae.lab.visualize.ok"),
        (["flow", "status", "--json"], "dae.flow.status.nothing"),
    ],
    ids=["lab_visualize", "flow_status"],
)
def test_post_noun_json_is_accepted(argv: list[str], code: str) -> None:
    """A trailing --json parses (exit 0) where it used to be an unknown option."""
    runner = CliRunner()
    with _isolated_cwd():
        result = runner.invoke(app, argv, prog_name="dae")
    assert result.exit_code == OK_EXIT, (
        f"expected success for post-noun --json, got exit "
        f"{result.exit_code}: {result.stdout!r} / {result.stderr!r}"
    )
    payload = json.loads(result.stdout)  # raises if stdout is not the machine object
    assert payload["code"] == code, payload


def test_global_pre_noun_json_succeeds_with_valid_json() -> None:
    """stdout parses as JSON and carries the visualize outcome code."""
    runner = CliRunner()
    result = runner.invoke(app, ["--json", "lab", "visualize"], prog_name="dae")
    assert result.exit_code == OK_EXIT, (
        f"expected success for pre-noun --json, got exit "
        f"{result.exit_code}: {result.stdout!r} / {result.stderr!r}"
    )
    payload = json.loads(result.stdout)  # raises if stdout is not the machine object
    assert payload["code"] == "dae.lab.visualize.ok"


def test_bare_json_envelope_is_exactly_the_four_keys() -> None:
    """error is always present, null on success; data holds the payload or null."""
    runner = CliRunner()
    result = runner.invoke(app, ["--json"], prog_name="dae")
    assert result.exit_code == OK_EXIT, (
        f"expected success for bare --json, got exit "
        f"{result.exit_code}: {result.stdout!r} / {result.stderr!r}"
    )
    payload = json.loads(result.stdout)
    assert set(payload) == {"code", "exit", "error", "data"}, payload
    assert payload["code"] == "dae.onboarding.ok"
    assert payload["exit"] == 0
    assert payload["error"] is None
    assert payload["data"] is None
