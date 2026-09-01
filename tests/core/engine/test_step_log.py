"""An isolated child's merged stdout and stderr land live in ``step.log``.

Mirrors test_subprocess_spike's fixtures and skips as a whole without ``uv``.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

import daedalus.flow as dae
from daedalus.core.engine import subprocess_runner
from tests._helpers import _step_ctx, _write_module

# Repo root (the editable daedalus source the child imports): tests/ -> repo.
_REPO_ROOT = Path(__file__).resolve().parents[3]
# The dir that exposes only the daedalus package: what a child gets on
# PYTHONPATH. Mirrors subprocess_runner._daedalus_import_root() for a checkout.
_IMPORT_ROOT = _REPO_ROOT / "src"

_UV = shutil.which("uv")
pytestmark = [
    pytest.mark.skipif(
        _UV is None, reason="uv launcher not on PATH; step-log capture needs it"
    ),
    pytest.mark.integration,
]


def test_child_stdout_is_captured_to_step_log(tmp_path: Path) -> None:
    marker = "hello from the child stdout stream"
    mod = _write_module(
        tmp_path / "prints",
        "import daedalus.flow as dae\n\n\n"
        "@dae.entry\n"
        "def prints(ctx: dae.FlowContext) -> None:\n"
        f"    print({marker!r})\n",
    )
    output_dir = tmp_path / "out"
    ctx = _step_ctx(
        output_dir=output_dir, input_dir=tmp_path, role=dae.Role.TRANSFORM, seed=1
    )

    result = subprocess_runner.run_step_subprocess(mod, ctx, import_root=_IMPORT_ROOT)

    assert result.returncode == 0, result.stderr
    assert result.status == "completed"
    log = output_dir / "step.log"
    assert log.is_file()
    assert marker in log.read_text(encoding="utf-8", errors="replace")


def test_silent_child_still_produces_step_log(tmp_path: Path) -> None:
    mod = _write_module(
        tmp_path / "quiet",
        "import daedalus.flow as dae\n\n\n"
        "@dae.entry\n"
        "def quiet(ctx: dae.FlowContext) -> None:\n"
        "    pass\n",
    )
    output_dir = tmp_path / "out"
    ctx = _step_ctx(
        output_dir=output_dir, input_dir=tmp_path, role=dae.Role.TRANSFORM, seed=1
    )

    result = subprocess_runner.run_step_subprocess(mod, ctx, import_root=_IMPORT_ROOT)

    assert result.returncode == 0, result.stderr
    assert result.status == "completed"
    assert (output_dir / "step.log").is_file()


def test_missing_package_recovered_from_merged_log(tmp_path: Path) -> None:
    """The ``DAE_MISSING_PACKAGE=`` marker is read back from the merged step.log."""
    mod = _write_module(
        tmp_path / "absent_pkg",
        "import no_such_pkg_dae_test\n\n"
        "import daedalus.flow as dae\n\n\n"
        "@dae.entry\n"
        "def absent_pkg(ctx: dae.FlowContext) -> None:\n"
        "    pass\n",
    )
    output_dir = tmp_path / "out"
    ctx = _step_ctx(
        output_dir=output_dir, input_dir=tmp_path, role=dae.Role.TRANSFORM, seed=1
    )

    result = subprocess_runner.run_step_subprocess(mod, ctx, import_root=_IMPORT_ROOT)

    assert result.status == "failed"
    assert result.missing_package == "no_such_pkg_dae_test"
    assert (output_dir / "step.log").is_file()


def test_failure_traceback_present_in_step_log(tmp_path: Path) -> None:
    mod = _write_module(
        tmp_path / "boom",
        "import daedalus.flow as dae\n\n\n"
        "@dae.entry\n"
        "def boom(ctx: dae.FlowContext) -> None:\n"
        "    raise RuntimeError('boom raised in the child')\n",
    )
    output_dir = tmp_path / "out"
    ctx = _step_ctx(
        output_dir=output_dir, input_dir=tmp_path, role=dae.Role.TRANSFORM, seed=1
    )

    result = subprocess_runner.run_step_subprocess(mod, ctx, import_root=_IMPORT_ROOT)

    assert result.returncode != 0
    assert result.status == "failed"
    log = output_dir / "step.log"
    assert log.is_file()
    assert "boom raised in the child" in log.read_text(
        encoding="utf-8", errors="replace"
    )


def test_read_step_log_tail_absent_log_returns_empty(tmp_path: Path) -> None:
    """A step dir with no ``step.log`` yields the empty string (never raises)."""
    assert subprocess_runner.read_step_log_tail(tmp_path) == ""


def test_read_step_log_tail_returns_only_last_n_lines(tmp_path: Path) -> None:
    """When the log has more than ``max_lines`` lines, only the last N come back."""
    lines = [f"line {i}" for i in range(50)]
    (tmp_path / "step.log").write_text("\n".join(lines) + "\n", encoding="utf-8")

    tail = subprocess_runner.read_step_log_tail(tmp_path, max_lines=5)

    assert tail == "\n".join(f"line {i}" for i in range(45, 50))


def test_read_step_log_tail_returns_all_when_fewer_than_n(tmp_path: Path) -> None:
    """When the log has fewer than ``max_lines`` lines, all of them come back."""
    (tmp_path / "step.log").write_text("only\ntwo\n", encoding="utf-8")

    tail = subprocess_runner.read_step_log_tail(tmp_path, max_lines=20)

    assert tail == "only\ntwo"
