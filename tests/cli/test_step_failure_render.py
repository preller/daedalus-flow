"""A failed step shows its code, a one-line cause, the last frame and a log path.

The full traceback goes to ``step-error.log``; driven over ``flight_one_fails``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from daedalus.cli.app import app
from daedalus.core import lineage
from tests._helpers import chdir
from tests.cli._cli_contract import (
    _copy_fixture_lab,
    _only_flow,
    _reset_json_state,
)

pytestmark = pytest.mark.integration

__all__ = ["_reset_json_state"]


def _run_human(lab_dir: Path, *args: str) -> str:
    """Text of ``dae <args>`` on the human path, captured at the ``out`` Console."""
    from daedalus.cli.console import out

    # `out` is bound to the real stdout at import, so CliRunner's redirect never
    # captures it; out.capture() intercepts at the Console level.
    runner = CliRunner()
    with chdir(lab_dir), out.capture() as captured:
        runner.invoke(app, [*args], prog_name="dae")
    return captured.get()


def _run_json(lab_dir: Path, *args: str) -> dict:
    """Invoke ``dae --json <args>`` in ``lab_dir`` and return the parsed payload."""
    runner = CliRunner()
    with chdir(lab_dir):
        result = runner.invoke(app, ["--json", *args], prog_name="dae")
    return json.loads(result.stdout)


def test_human_render_shows_code_cause_last_frame_and_log_path(tmp_path: Path) -> None:
    """The render shows code, one-line cause, last frame and log path only."""
    lab = _copy_fixture_lab("flight_one_fails", tmp_path)
    out = _run_human(lab, "lab", "run")

    # The stable per-step code and a one-line cause are named.
    assert "dae.step.execution_failed" in out
    assert "work failed for item 20" in out
    # The last traceback frame (the module that raised) is shown inline.
    assert "RuntimeError" in out
    # A pointer to the on-disk full traceback is printed.
    assert "step-error.log" in out
    # The full multi-frame traceback is not dumped inline; the "Traceback (most
    # recent call last)" header belongs to the file only.
    assert "Traceback (most recent call last)" not in out


def test_step_error_log_holds_full_traceback(tmp_path: Path) -> None:
    """``step-error.log`` exists beside the failed step output with the full trace."""
    lab = _copy_fixture_lab("flight_one_fails", tmp_path)
    _run_human(lab, "lab", "run")

    logs = list(lab.rglob("step-error.log"))
    assert logs, "expected a step-error.log beside the failed step output"
    full = logs[0].read_text()
    assert "Traceback (most recent call last)" in full
    assert "RuntimeError" in full
    assert "work failed for item 20" in full


def test_json_error_cause_carries_code_and_module(tmp_path: Path) -> None:
    """The --json ``error`` cause names the code and module, keeping error/reason."""
    lab = _copy_fixture_lab("flight_one_fails", tmp_path)
    payload = _run_json(lab, "lab", "run")

    assert payload["code"] == "dae.lab.run.failed"
    assert payload["exit"] == 1
    cause = payload["error"]
    assert cause is not None
    assert cause["code"] == "dae.step.execution_failed"
    # The module slot names the failed step instance.
    assert "work" in cause["module"]
    # The pre-existing keys are unchanged (additive enrichment).
    assert "work failed for item 20" in cause["error"]
    assert "work failed for item 20" in cause["reason"]

    # The lineage carries the same code on the failed step.
    record = lineage.read_flow_record(_only_flow(lab))
    failed = next(s for s in record.steps if s.status == "failed")
    assert failed.error_code == "dae.step.execution_failed"
