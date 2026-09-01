"""PrefectEngine progress lines, from Starting through the (k/N) counter to the summary.

The line tests run a child ``dae lab run`` and read Prefect's logging off its stderr.
"""

from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from daedalus.core.engine import prefect as pf
from tests._helpers import fixtures_root


def test_progress_counter_is_monotonic_and_gapless_single_threaded() -> None:
    nxt = pf._make_progress_counter()
    assert [nxt() for _ in range(5)] == [1, 2, 3, 4, 5]


def test_progress_counter_reaches_exactly_n_under_concurrent_callers() -> None:
    """Prefect settles tasks on several threads, so the counter must be atomic."""
    n = 200
    nxt = pf._make_progress_counter()
    results: list[int] = []
    lock = threading.Lock()  # guards only the test's result list, not the counter
    ready = threading.Barrier(n)

    def worker() -> None:
        ready.wait()  # release all threads at once to maximize contention
        value = nxt()
        with lock:
            results.append(value)

    threads = [threading.Thread(target=worker) for _ in range(n)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(results) == list(range(1, n + 1))
    assert len(set(results)) == n  # no two callers saw the same k
    assert max(results) == n  # the counter ends exactly at N


class _SpyLogger:
    """Minimal stand-in for Prefect's run logger: records ``error`` messages."""

    def __init__(self) -> None:
        self.errors: list[str] = []

    def error(self, message: str) -> None:
        self.errors.append(message)


def test_failure_tail_logs_the_last_lines_when_a_step_log_exists(
    tmp_path: Path,
) -> None:
    """The tail names the instance id and carries the last line of step.log."""
    (tmp_path / "step.log").write_text("\n".join(f"line {i}" for i in range(50)))
    spy = _SpyLogger()
    pf._log_failure_tail(spy, "fit_mcmc@w3", tmp_path)
    assert len(spy.errors) == 1
    assert "fit_mcmc@w3" in spy.errors[0]
    assert "line 49" in spy.errors[0]  # the very last line rides in the tail


def test_failure_tail_stays_silent_for_an_ambient_step_with_no_log(
    tmp_path: Path,
) -> None:
    spy = _SpyLogger()
    pf._log_failure_tail(spy, "fit_mcmc@w3", tmp_path)
    assert spy.errors == []


_HAS_PREFECT = importlib.util.find_spec("prefect") is not None

# Instance ids carry an "@" (``debug_io@w2``), which keeps the patterns off
# Prefect's own lines ("Starting temporary server").
_STARTING_RE = re.compile(r"Starting (\S+@\S+)")
_SETTLED_RE = re.compile(r"(Finished|Failed) (\S+@\S+) in ([\d.]+)s \((\d+)/(\d+)\)")
_SUMMARY_RE = re.compile(r"Lab finished: (\d+) steps in ([\d.]+)s")

_RAISING_STEP = (
    "import daedalus.flow as dae\n\n\n"
    "@dae.entry\n"
    "def sleep_briefly(ctx: dae.FlowContext) -> None:\n"
    '    raise RuntimeError("sleep_briefly raised by the test")\n'
)


def _copy_linear_smoke(dest: Path) -> Path:
    """Copy the linear_smoke fixture lab into ``dest`` with ``engine: prefect`` set."""
    import shutil

    lab = dest / "lab"
    shutil.copytree(
        fixtures_root() / "labs" / "linear_smoke",
        lab,
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    body = (lab / "lab.yaml").read_text()
    (lab / "lab.yaml").write_text(f"engine: prefect\n{body}")
    return lab


def _run_human(lab: Path, home: Path) -> subprocess.CompletedProcess[str]:
    """Run ``dae lab run`` in human mode in a child and capture its stderr."""
    import daedalus

    # A bare interpreter, not ``uv run``, has no editable install of daedalus, so
    # PYTHONPATH points at the source root and the child imports this package.
    src_root = Path(daedalus.__file__).resolve().parent.parent
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join(
            [str(src_root), os.environ.get("PYTHONPATH", "")]
        ).rstrip(os.pathsep),
        "PREFECT_HOME": str(home),
        "PREFECT_SERVER_ALLOW_EPHEMERAL_MODE": "true",
        "PREFECT_LOGGING_TO_API_ENABLED": "false",
        "PREFECT_SERVER_ANALYTICS_ENABLED": "false",
        "DO_NOT_TRACK": "1",
    }
    # `PREFECT_LOGGING_LEVEL` stays unset; the engine defaults it to INFO, which puts
    # the progress lines on stderr.
    code = (
        "import sys; from daedalus.cli import main; "
        "sys.argv = ['dae', 'lab', 'run']; main()"
    )
    return subprocess.run(  # noqa: S603 (fixed argv: this interpreter + -c probe)
        [sys.executable, "-c", code],
        cwd=lab,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=240,
    )


pytestmark = [
    pytest.mark.skipif(
        not _HAS_PREFECT,
        reason="the optional daedalus-flow[engine] extra (prefect) is not installed",
    ),
    pytest.mark.integration,
    pytest.mark.slow,
]


def test_each_step_logs_a_starting_line_then_a_finished_line(tmp_path: Path) -> None:
    lab = _copy_linear_smoke(tmp_path)
    result = _run_human(lab, tmp_path / "home")
    assert result.returncode == 0, result.stderr

    started = _STARTING_RE.findall(result.stderr)
    settled = _SETTLED_RE.findall(result.stderr)
    assert started, f"no 'Starting <id>' lines on stderr:\n{result.stderr}"

    finished_ids = {sid for verb, sid, *_ in settled if verb == "Finished"}
    assert set(started) == finished_ids, (set(started), finished_ids)

    # Starting precedes Finished for each id.
    for sid in started:
        start_at = result.stderr.index(f"Starting {sid}")
        finish_at = result.stderr.index(f"Finished {sid} in ")
        assert start_at < finish_at, f"'{sid}' finished before it started"


def test_finished_lines_carry_elapsed_and_a_counter_ending_at_n_over_n(
    tmp_path: Path,
) -> None:
    """k covers 1..N without gaps, N agrees across lines, and the summary reports N."""
    lab = _copy_linear_smoke(tmp_path)
    result = _run_human(lab, tmp_path / "home")
    assert result.returncode == 0, result.stderr

    settled = _SETTLED_RE.findall(result.stderr)
    assert settled, f"no settled progress lines on stderr:\n{result.stderr}"

    elapsed = [float(e) for _, _, e, _, _ in settled]
    assert all(value >= 0.0 for value in elapsed)  # measured wall time

    totals = {int(total) for *_, total in settled}
    assert len(totals) == 1, f"N disagreed across lines: {totals}"
    (n,) = totals
    ks = sorted(int(k) for *_head, k, _total in settled)
    assert ks == list(range(1, n + 1)), (ks, n)  # 1..N, gap-free, ends at N

    summary = _SUMMARY_RE.search(result.stderr)
    assert summary is not None, f"no 'Lab finished' summary:\n{result.stderr}"
    assert int(summary.group(1)) == n  # the summary's N matches the per-step N


def test_a_failing_step_logs_a_failed_line_and_the_run_still_fails(
    tmp_path: Path,
) -> None:
    """The Failed line carries the counter and follows the step's Starting line."""
    lab = _copy_linear_smoke(tmp_path)
    (lab / "modules" / "sleep_briefly" / "main.py").write_text(_RAISING_STEP)

    result = _run_human(lab, tmp_path / "home")
    assert result.returncode != 0, f"a raising step must fail the run:\n{result.stderr}"

    settled = _SETTLED_RE.findall(result.stderr)
    failed = [
        (sid, k, total) for verb, sid, _e, k, total in settled if verb == "Failed"
    ]
    assert failed, f"no 'Failed <id>' progress line on stderr:\n{result.stderr}"
    failed_id = failed[0][0]
    assert failed_id.startswith("sleep_briefly@"), failed_id

    # The failing step announced itself before it failed.
    start_at = result.stderr.index(f"Starting {failed_id}")
    fail_at = result.stderr.index(f"Failed {failed_id} in ")
    assert start_at < fail_at


_RAISING_STEP_WITH_OUTPUT = (
    "import daedalus.flow as dae\n\n\n"
    "@dae.entry\n"
    "def sleep_briefly(ctx: dae.FlowContext) -> None:\n"
    '    print("live progress line from sleep_briefly")\n'
    '    raise RuntimeError("sleep_briefly raised by the test")\n'
)


def _copy_linear_smoke_isolated(dest: Path) -> Path:
    """linear_smoke under prefect with ``isolation: uv``; every step tees a step.log."""
    lab = _copy_linear_smoke(dest)
    body = (lab / "lab.yaml").read_text()
    (lab / "lab.yaml").write_text(f"isolation: uv\n{body}")
    return lab


def test_a_failing_isolated_step_surfaces_its_captured_output_tail(
    tmp_path: Path,
) -> None:
    lab = _copy_linear_smoke_isolated(tmp_path)
    raising = lab / "modules" / "sleep_briefly" / "main.py"
    raising.write_text(_RAISING_STEP_WITH_OUTPUT)

    result = _run_human(lab, tmp_path / "home")
    assert result.returncode != 0, result.stderr
    assert "Last output from sleep_briefly@" in result.stderr, result.stderr
    assert "live progress line from sleep_briefly" in result.stderr, result.stderr
