"""CLI contract tests for ``flow status`` read-back and run step timing."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from daedalus.cli import console as cli_console
from daedalus.cli.app import app
from tests._helpers import chdir
from tests.cli._cli_contract import (
    OK_EXIT,
    _copy_fixture_lab,
    _json_code,
    _only_flow,
    _reset_json_state,
    _run_cli_in,
    run_cli,
)

pytestmark = pytest.mark.integration  # integration tier, CLI command chains

# Re-export imported fixtures so flake8/ruff do not flag them as unused; pytest
# resolves them by name in this module's namespace.
__all__ = ["_reset_json_state"]


def test_flow_status_nothing_in_empty_cwd() -> None:
    """`flow status` with no dae-outputs/flows/ is a valid empty query (exit 0)."""
    assert run_cli("flow", "status") == (OK_EXIT, "dae.flow.status.nothing")


def test_flow_status_ok_after_real_run(tmp_path: Path) -> None:
    """The status payload names the flow just written, so it is a true read-back."""
    lab = _copy_fixture_lab("linear_smoke", tmp_path)
    assert _run_cli_in(lab, "lab", "run") == (OK_EXIT, "dae.lab.run.ok")

    flow_id = _only_flow(lab).name
    runner = CliRunner()
    with chdir(lab):
        result = runner.invoke(app, ["--json", "flow", "status"], prog_name="dae")
    assert (result.exit_code, _json_code(result)) == (OK_EXIT, "dae.flow.status.ok")
    payload = json.loads(result.stdout)["data"]  # the envelope nests it under data
    assert payload["flow_id"] == flow_id
    assert payload["status"] == "completed"


def test_flow_status_prints_stable_triple(tmp_path: Path) -> None:
    """After a diamond_join run, each walks row carries the stable triple."""
    lab = _copy_fixture_lab("diamond_join", tmp_path)
    assert _run_cli_in(lab, "lab", "run") == (OK_EXIT, "dae.lab.run.ok")

    runner = CliRunner()
    with chdir(lab):
        result = runner.invoke(app, ["--json", "flow", "status"], prog_name="dae")
    assert (result.exit_code, _json_code(result)) == (OK_EXIT, "dae.flow.status.ok")
    payload = json.loads(result.stdout)["data"]  # the envelope nests it under data

    walks = payload["walks"]
    assert [w["walk_id"] for w in walks] == ["w1", "w2", "w3"]
    for record in walks:
        # the stable triple is present on every row, alongside walk_id and the
        # user_walk bridge key.
        assert set(record) >= {
            "walk_id",
            "flight_id",
            "born_at",
            "branch_module",
            "user_walk",
        }
    # the two branch walks name a branch_module (born at the brancher edge); the
    # global root walk carries none.
    by_id = {w["walk_id"]: w for w in walks}
    assert by_id["w1"]["branch_module"] is None
    assert by_id["w2"]["branch_module"] is not None
    assert by_id["w3"]["branch_module"] is not None


def test_lab_run_json_exposes_step_timing(tmp_path: Path) -> None:
    """Each step carries started_at and finished_at; both non-null once completed."""
    lab = _copy_fixture_lab("linear_smoke", tmp_path)
    runner = CliRunner()
    with chdir(lab):
        result = runner.invoke(app, ["--json", "lab", "run"], prog_name="dae")
    assert result.exit_code == OK_EXIT, result.stdout
    data = json.loads(result.stdout)
    assert data["code"] == "dae.lab.run.ok"
    steps = data["data"]["steps"]
    assert steps, "expected at least one step in the flow payload"
    for step in steps:
        assert "started_at" in step, f"step missing started_at: {step}"
        assert "finished_at" in step, f"step missing finished_at: {step}"
        if step["status"] == "completed":
            assert step["started_at"] is not None, f"completed step null start: {step}"
            assert step["finished_at"] is not None, (
                f"completed step null finish: {step}"
            )


def _status_chrome(lab: Path) -> str:
    """The stderr chrome of ``dae flow status``, captured by swapping ``err.file``."""
    import io

    # `err` binds the real sys.stderr at import, so CliRunner's redirection
    # misses it; swapping the file captures the Next chrome.
    buf = io.StringIO()
    old = cli_console.err.file
    cli_console.err.file = buf
    try:
        runner = CliRunner()
        with chdir(lab):
            runner.invoke(app, ["flow", "status"], prog_name="dae")
    finally:
        cli_console.err.file = old
    return buf.getvalue()


def test_flow_status_completed_omits_resume_hint(tmp_path: Path) -> None:
    """Resume re-runs failed steps only, so a completed flow gets no resume hint."""
    lab = _copy_fixture_lab("linear_smoke", tmp_path)
    assert _run_cli_in(lab, "lab", "run") == (OK_EXIT, "dae.lab.run.ok")

    chrome = _status_chrome(lab)
    assert "dae flow resume" not in chrome, (
        f"completed flow must not advertise resume; got chrome:\n{chrome}"
    )


def test_flow_status_failed_shows_resume_hint(tmp_path: Path) -> None:
    """flight_one_fails leaves a failed flow, so the Next hint names resume."""
    lab = _copy_fixture_lab("flight_one_fails", tmp_path)
    # The run itself fails (exit 1); the lineage recording `failed` is what counts.
    _run_cli_in(lab, "lab", "run")

    chrome = _status_chrome(lab)
    assert "dae flow resume" in chrome, (
        f"failed flow must advertise resume; got chrome:\n{chrome}"
    )


def test_flow_status_help_states_read_only_contract() -> None:
    """status reports and never gates; it exits 0 even for a failed flow."""
    runner = CliRunner()
    result = runner.invoke(app, ["flow", "status", "--help"], prog_name="dae")
    assert result.exit_code == OK_EXIT
    help_text = " ".join(result.stdout.split())
    assert "read-only" in help_text.lower()
    assert "exits 0" in help_text.lower()
