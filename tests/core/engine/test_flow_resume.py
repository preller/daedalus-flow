"""``dae flow resume`` continues a failed flow in place.

A toggle ``gate`` transform in linear_smoke raises only while ``DAE_TEST_BOOM`` is set.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from tests._helpers import _daedalus, _run_cli_in, _run_once_dirs, fixtures_root
from tests.core.engine._local_engine import _only_flow

_FIXTURE_LABS = fixtures_root() / "labs"
OK_EXIT, FAILURE_EXIT, USAGE_EXIT = 0, 1, 2

# A transparent transform that raises only while `DAE_TEST_BOOM` is set; otherwise
# it copies every input file through unchanged.
_GATE_MAIN = (
    "import os\n"
    "import shutil\n"
    "import daedalus.flow as dae\n\n\n"
    "@dae.entry\n"
    "def gate(ctx: dae.FlowContext) -> None:\n"
    '    if os.environ.get("DAE_TEST_BOOM"):\n'
    '        raise RuntimeError("boom: toggled failure for the resume test")\n'
    "    for item in ctx.step_input_path.iterdir():\n"
    "        shutil.copy2(item, ctx.step_output_path / item.name)\n"
)

# The full run-once census once the flow completes; gate sits at 03 on walk w2.
_COMPLETE_DIRS = [
    "w1/01_emit_ticks",
    "w1/06_collect_report",
    "w2/02_debug_io",
    "w2/03_gate",
    "w2/04_sleep_briefly",
    "w2/05_summarize_walk",
]


def _lab_with_gate(tmp_path: Path) -> Path:
    """Copy linear_smoke and insert ``gate`` between debug_io and sleep_briefly."""
    src = _FIXTURE_LABS / "linear_smoke"
    lab = tmp_path / "linear_smoke"
    shutil.copytree(src, lab, ignore=shutil.ignore_patterns("__pycache__"))
    gate = lab / "modules" / "gate"
    gate.mkdir()
    (gate / "dae-module.yaml").write_text("role: transform\n")
    (gate / "main.py").write_text(_GATE_MAIN)
    text = (lab / "lab.yaml").read_text()
    text = text.replace(
        "  - id: sleep_briefly\n    depends: [debug_io]\n",
        "  - id: gate\n    depends: [debug_io]\n"
        "  - id: sleep_briefly\n    depends: [gate]\n",
    )
    (lab / "lab.yaml").write_text(text)
    return lab


def _flow_status(lab: Path) -> str:
    return json.loads((_only_flow(lab) / "dae-flow.json").read_text())["status"]


def _manifest(lab: Path, rel: str) -> dict:
    return json.loads((_daedalus(lab) / rel / "dae-manifest.json").read_text())


def _drive_to_failure(lab: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Run the lab once with the gate tripped; it fails at w2/03_gate."""
    monkeypatch.setenv("DAE_TEST_BOOM", "1")
    run = _run_cli_in(lab, "lab", "run")
    monkeypatch.delenv("DAE_TEST_BOOM", raising=False)
    assert run == (FAILURE_EXIT, "dae.lab.run.failed")
    assert _flow_status(lab) == "failed"
    assert _manifest(lab, "w2/03_gate")["status"] == "failed"
    # downstream of the gate never ran on the failed run
    assert "w2/04_sleep_briefly" not in _run_once_dirs(lab)


def test_flow_resume_completes_a_failed_flow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """resume continues a FAILED flow to completion (the gate now succeeds)."""
    lab = _lab_with_gate(tmp_path)
    _drive_to_failure(lab, monkeypatch)
    flow_id_before = _only_flow(lab).name

    resume = _run_cli_in(lab, "flow", "resume")

    assert resume == (OK_EXIT, "dae.flow.resume.ok")
    assert _flow_status(lab) == "completed"
    # the same flow continued; resume did not spawn a new flow
    assert _only_flow(lab).name == flow_id_before
    # the failed step re-ran (now completed) and everything downstream ran
    assert _manifest(lab, "w2/03_gate")["status"] == "completed"
    assert _run_once_dirs(lab) == _COMPLETE_DIRS


def test_flow_resume_does_not_rerun_completed_steps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Already-COMPLETED steps keep their artifacts: resume does not touch them."""
    lab = _lab_with_gate(tmp_path)
    _drive_to_failure(lab, monkeypatch)
    # the manifest files of the two steps that completed before the gate failed
    emit = _daedalus(lab) / "w1/01_emit_ticks" / "dae-manifest.json"
    debug = _daedalus(lab) / "w2/02_debug_io" / "dae-manifest.json"
    emit_mtime, debug_mtime = emit.stat().st_mtime_ns, debug.stat().st_mtime_ns

    _run_cli_in(lab, "flow", "resume")

    # not rewritten => not re-executed (a fresh run would touch the manifest)
    assert emit.stat().st_mtime_ns == emit_mtime
    assert debug.stat().st_mtime_ns == debug_mtime


def test_flow_resume_with_no_prior_flow_reports_nothing_to_resume(
    tmp_path: Path,
) -> None:
    """resume in a lab that has never run reports nothing to resume."""
    lab = _lab_with_gate(tmp_path)
    assert _run_cli_in(lab, "flow", "resume") == (OK_EXIT, "dae.flow.resume.nothing")


def test_flow_resume_when_flow_already_complete_reports_nothing_to_resume(
    tmp_path: Path,
) -> None:
    """A completed flow has nothing to resume, and that is not an error."""
    lab = _lab_with_gate(tmp_path)  # gate is transparent without the env var
    assert _run_cli_in(lab, "lab", "run") == (OK_EXIT, "dae.lab.run.ok")
    assert _run_cli_in(lab, "flow", "resume") == (OK_EXIT, "dae.flow.resume.nothing")


def test_flow_resume_that_fails_again_reports_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When the re-run step fails again, resume reports failure."""
    lab = _lab_with_gate(tmp_path)
    _drive_to_failure(lab, monkeypatch)

    # the toggle stays tripped on resume, so the gate fails again.
    monkeypatch.setenv("DAE_TEST_BOOM", "1")
    resume = _run_cli_in(lab, "flow", "resume")
    monkeypatch.delenv("DAE_TEST_BOOM", raising=False)

    assert resume == (FAILURE_EXIT, "dae.flow.resume.failed")
    assert _flow_status(lab) == "failed"
    assert _manifest(lab, "w2/03_gate")["status"] == "failed"
