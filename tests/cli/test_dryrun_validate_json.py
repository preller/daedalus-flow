"""The ``--json`` payloads of ``lab run --dry-run`` and ``lab validate``.

``lab run --dry-run`` carries a ``plan`` array; ``lab validate`` a ``recipe`` summary.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from daedalus.cli.app import app
from tests._helpers import chdir
from tests.cli._cli_contract import _isolated_cwd, _reset_json_state

pytestmark = pytest.mark.integration

__all__ = ["_reset_json_state"]


def _payload_in_scaffold(example: str, *args: str) -> dict:
    """Scaffold ``example`` in an isolated cwd; run ``args`` from inside the lab."""
    runner = CliRunner()
    with _isolated_cwd() as cwd:
        scaffold = runner.invoke(app, ["example", example], prog_name="dae")
        assert scaffold.exit_code == 0, f"scaffold failed: {scaffold.stdout}"
        with chdir(Path(cwd) / example):
            result = runner.invoke(app, ["--json", *args], prog_name="dae")
    assert result.exit_code == 0, (
        f"command failed (exit {result.exit_code}): {result.stdout}"
    )
    return json.loads(result.stdout)


def test_dry_run_json_carries_plan_array() -> None:
    """``dae --json lab run --dry-run`` on ensemble attaches a non-empty plan array."""
    payload = _payload_in_scaffold("ensemble", "lab", "run", "--dry-run")

    # The envelope stays byte-stable.
    assert payload["code"] == "dae.lab.run.dry_run"
    assert payload["exit"] == 0

    plan = payload["data"]["plan"]
    assert isinstance(plan, list) and plan, "plan must be a non-empty list"

    first = plan[0]
    assert {"order", "module", "role"} <= set(first.keys()), first
    # ensemble's emitter module is named "emit"; it is step one with role emitter.
    assert first["module"] == "emit", first
    assert first["role"] == "emitter", first
    modules = [row["module"] for row in plan]
    assert "emit" in modules, modules
    # order is the 1-based step index, ascending and contiguous.
    assert [row["order"] for row in plan] == list(range(1, len(plan) + 1))


def test_validate_json_carries_recipe_summary() -> None:
    """``dae --json lab validate`` on minimal attaches a recipe summary."""
    payload = _payload_in_scaffold("minimal", "lab", "validate")

    # The envelope stays byte-stable.
    assert payload["code"] == "dae.lab.validate.ok"
    assert payload["exit"] == 0

    recipe_summary = payload["data"]["recipe"]
    assert isinstance(recipe_summary, dict), recipe_summary
    assert recipe_summary["modules"] >= 1, recipe_summary
    # minimal has one module, so it is both the graph source and the sink.
    assert recipe_summary["source"] == "normalize", recipe_summary
    assert recipe_summary["sink"] == "normalize", recipe_summary


def test_validate_json_always_carries_recipe_key() -> None:
    """The no-lab exemplar fallback carries ``recipe: null`` rather than no key."""
    runner = CliRunner()
    with _isolated_cwd():
        result = runner.invoke(app, ["--json", "lab", "validate"], prog_name="dae")
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["code"] == "dae.lab.validate.ok"
    assert payload["data"] is not None, "validate.ok must carry a data payload"
    assert "recipe" in payload["data"], "recipe key must be present on every ok"
    assert payload["data"]["recipe"] is None  # no specific recipe was validated
