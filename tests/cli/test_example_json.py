"""``dae --json example`` carries an ``examples`` array, one entry per ladder row.

The array is built from ``strings.example_rows``, the same source as the human ladder.
"""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from daedalus.cli import strings
from daedalus.cli.app import app
from tests.cli._cli_contract import OK_EXIT, _isolated_cwd, _reset_json_state

pytestmark = pytest.mark.integration  # integration tier, CLI surface contract

# Re-export the autouse fixture so ruff does not flag the import as unused; pytest
# resolves it by name in this module's namespace.
__all__ = ["_reset_json_state"]


def test_json_example_list_carries_examples_array() -> None:
    """Length equals the ladder; each item has name, available and description."""
    runner = CliRunner()
    result = runner.invoke(app, ["--json", "example"], prog_name="dae")
    assert result.exit_code == OK_EXIT, (
        f"expected success, got exit {result.exit_code}: "
        f"{result.stdout!r} / {result.stderr!r}"
    )
    payload = json.loads(result.stdout)  # raises if stdout is not the machine object

    # The pre-existing keys are unchanged.
    assert payload["code"] == "dae.example.list.ok"
    assert payload["exit"] == 0

    examples = payload["data"]["examples"]
    assert isinstance(examples, list)
    # One entry per ladder row, the same rows the human render reads.
    assert len(examples) == len(strings.example_rows())
    assert len(examples) == len(strings.KNOWN_EXAMPLES)

    names = [item["name"] for item in examples]
    # Ladder order is preserved (simplest first), matching KNOWN_EXAMPLES.
    assert names == list(strings.KNOWN_EXAMPLES)

    for item in examples:
        assert set(item) >= {"name", "available", "description"}
        assert isinstance(item["name"], str) and item["name"]
        assert isinstance(item["available"], bool)
        assert isinstance(item["description"], str) and item["description"]
        # availability agrees with AVAILABLE_EXAMPLES.
        assert item["available"] == (item["name"] in strings.AVAILABLE_EXAMPLES)


def test_json_example_scaffold_still_valid_json() -> None:
    """The scaffold path keeps paths, code and exit after the list enrichment."""
    runner = CliRunner()
    with _isolated_cwd():
        result = runner.invoke(app, ["--json", "example", "minimal"], prog_name="dae")
    assert result.exit_code == OK_EXIT, (
        f"expected success, got exit {result.exit_code}: "
        f"{result.stdout!r} / {result.stderr!r}"
    )
    payload = json.loads(result.stdout)
    assert payload["code"] == "dae.example.scaffold.ok"
    assert payload["exit"] == 0
    assert isinstance(payload["data"]["paths"], list) and payload["data"]["paths"]
