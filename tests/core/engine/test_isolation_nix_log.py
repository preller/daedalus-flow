"""A nix build failure raises a distilled cause and saves the full log to a file.

``distill_nix_log`` and ``_nix_build`` are pure units here; no nix is needed.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from daedalus.core.engine.isolation import (
    _NIX_LOG_NAME,
    NixProvisionError,
    _nix_build,
    distill_nix_log,
)

# A raw nix builder stream: 200 lines of copy chatter with the cause, a read-only
# file system, near the end.
_BULK_LINES = [
    f"copying path '/nix/store/{i:040x}-dep-{i}' from 'https://cache.nixos.org'"
    for i in range(200)
]
_DRV = "/nix/store/abcd-env.drv"
_RAW_NIX_LOG = "\n".join(
    [
        "warning: ignoring untrusted substituter",
        *_BULK_LINES,
        f"building {_DRV!r}...",
        '@nix { "action": "start", "id": 7 }',
        f"error: builder for {_DRV!r} failed with exit code 1;",
        "       last 3 log lines:",
        "       > mkdir: cannot create directory '/nix/store/xyz': "
        "Read-only file system",
        f"       For full logs, run 'nix log {_DRV}'.",
    ]
)


def test_distill_keeps_the_real_cause() -> None:
    short = distill_nix_log(_RAW_NIX_LOG)
    assert "Read-only file system" in short
    assert "error: builder for" in short


def test_distill_drops_the_bulk() -> None:
    short = distill_nix_log(_RAW_NIX_LOG)
    # The 200 copy-path lines are the bulk; the distilled text must shed them.
    assert short.count("\n") < 20
    assert "copying path" not in short
    assert len(short) < len(_RAW_NIX_LOG)


def test_distill_is_total_on_empty_and_blankish_input() -> None:
    # A build that failed with no stderr must not crash the distiller.
    assert isinstance(distill_nix_log(""), str)
    assert isinstance(distill_nix_log("   \n\n  "), str)


def test_distill_without_error_line_falls_back_to_the_tail() -> None:
    # With no "error:" marker the trailing lines are kept and the bulk head is shed.
    raw = "\n".join([*_BULK_LINES, "the-meaningful-tail-line"])
    short = distill_nix_log(raw)
    assert "the-meaningful-tail-line" in short
    # The bulk head (the first copy lines) is dropped; the result is short.
    assert _BULK_LINES[0] not in short
    assert short.count("\n") < 20
    assert len(short) < len(raw)


def test_nix_build_saves_full_log_and_raises_distilled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log_dir = tmp_path / "step_output"
    log_dir.mkdir()

    def _fake_run(*_args, **_kwargs):
        return subprocess.CompletedProcess(
            args=["nix", "build"], returncode=1, stdout="", stderr=_RAW_NIX_LOG
        )

    monkeypatch.setattr(subprocess, "run", _fake_run)

    with pytest.raises(NixProvisionError) as excinfo:
        _nix_build(tmp_path / "flake", log_dir=log_dir)

    message = str(excinfo.value)
    # The raised message is the distilled text plus a pointer, never the full stream.
    assert "Read-only file system" in message
    assert "copying path" not in message
    # The full raw stream is saved verbatim to the log file under log_dir...
    log_file = log_dir / _NIX_LOG_NAME
    assert log_file.is_file()
    saved = log_file.read_text()
    assert saved == _RAW_NIX_LOG
    assert "copying path" in saved
    # ...and the raised message points at that saved log.
    assert _NIX_LOG_NAME in message


def test_nix_build_without_log_dir_still_raises_distilled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # log_dir is optional (provision can run without a flow ctx); the message is
    # still the distilled cause, never the full stream, even with no file to save.
    def _fake_run(*_args, **_kwargs):
        return subprocess.CompletedProcess(
            args=["nix", "build"], returncode=1, stdout="", stderr=_RAW_NIX_LOG
        )

    monkeypatch.setattr(subprocess, "run", _fake_run)

    with pytest.raises(NixProvisionError) as excinfo:
        _nix_build(tmp_path / "flake")

    message = str(excinfo.value)
    assert "Read-only file system" in message
    assert "copying path" not in message
