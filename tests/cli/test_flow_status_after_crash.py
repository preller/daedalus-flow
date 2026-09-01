"""``dae flow status`` reports a run stranded as ``running`` by a crash as ``failed``.

Status stays read-only and exits 0; the assertion is on the rendered and --json status.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from typer.testing import CliRunner

from daedalus.cli.app import app
from daedalus.core import lineage
from tests._helpers import chdir
from tests.cli._cli_contract import (
    _copy_fixture_lab,
    _human_stdout,
    _only_flow,
    _reset_json_state,
)

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.integration

# Re-export the autouse fixture so ruff does not flag it; pytest resolves by name.
__all__ = ["_reset_json_state"]

# A pid that can never name a live process: pid_max is the highest assignable
# pid, so one above it is a stable stand-in for a crashed worker.
_DEAD_PID = 2**22 + 7


def _strand_as_running(flow_dir: Path) -> None:
    """Overwrite a flow's record with a ``running`` one owned by a dead pid."""
    # Simulates a worker killed mid-step with no handler run, as after a kill.
    prior = lineage.read_flow_record(flow_dir)
    stranded = lineage.FlowRecord(
        flow_id=prior.flow_id,
        lab_name=prior.lab_name,
        status="running",
        created_at=prior.created_at,
        steps=tuple(
            lineage.FlowStep(step_id=step.step_id, status="running")
            for step in prior.steps
        ),
        walks=prior.walks,
        engine=prior.engine,
        max_workers=prior.max_workers,
        owner_pid=_DEAD_PID,
        owner_create_time=1.0,
    )
    lineage.write_flow_record(flow_dir, stranded)


def test_flow_status_reports_a_crashed_run_as_failed(tmp_path: Path) -> None:
    """The --json status reads failed with exit 0, and the record is rewritten."""
    lab = _copy_fixture_lab("linear_smoke", tmp_path)
    runner = CliRunner()
    with chdir(lab):
        run = runner.invoke(app, ["--json", "lab", "run"], prog_name="dae")
    assert json.loads(run.stdout)["code"] == "dae.lab.run.ok"

    flow_dir = _only_flow(lab)
    _strand_as_running(flow_dir)
    # The record now claims to be running.
    assert lineage.read_flow_record(flow_dir).status == "running"

    with chdir(lab):
        status = runner.invoke(app, ["--json", "flow", "status"], prog_name="dae")
    payload = json.loads(status.stdout)

    assert status.exit_code == 0
    assert payload["code"] == "dae.flow.status.ok"
    assert payload["data"]["status"] == "failed"
    assert payload["data"]["status"] != "running"
    # The envelope error names a cause, not a bare failed.
    assert payload["error"]

    # Reconcile-on-read rewrote the file: a fresh pure read agrees.
    assert lineage.read_flow_record(flow_dir).status == "failed"


def test_flow_status_human_render_shows_failed_for_a_crash(tmp_path: Path) -> None:
    """The human render is a pure render of the reconciled record."""
    lab = _copy_fixture_lab("linear_smoke", tmp_path)
    runner = CliRunner()
    with chdir(lab):
        runner.invoke(app, ["--json", "lab", "run"], prog_name="dae")
    _strand_as_running(_only_flow(lab))

    # The render goes through the module-level rich Console, not CliRunner's
    # stdout, so capture at the Console level (the shared human-output helper).
    with chdir(lab):
        rendered = _human_stdout(runner, ["flow", "status"]).lower()

    assert "failed" in rendered
    assert "running" not in rendered
