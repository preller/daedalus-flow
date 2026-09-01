"""Unit tests for the journey ``_dae`` driver's ``--json`` parsing.

Monkeypatched, no installed binary or subprocess, so they run in the fast tier.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.journey import _journey


def _patch_run(
    monkeypatch: pytest.MonkeyPatch, *, stdout: str, returncode: int = 0
) -> None:
    """Make ``_dae`` see a fixed (returncode, stdout) without running the binary."""
    # Path(__file__) exists, so _dae's ``DAE.exists()`` precondition holds; the
    # str(DAE) argv is never executed because subprocess.run is stubbed.
    monkeypatch.setattr(_journey, "DAE", Path(__file__))
    monkeypatch.setattr(
        "tests.journey._journey.subprocess.run",
        lambda *a, **k: SimpleNamespace(
            returncode=returncode, stdout=stdout, stderr=""
        ),
    )


@pytest.mark.parametrize(
    "stdout",
    [
        "not json at all",  # JSONDecodeError
        "",  # empty stdout
        '{"status": "ok", "exit": 0}',  # JSON object, no "code" key
        "[1, 2, 3]",  # JSON, but not an object
        "null",  # JSON null, not an object
    ],
)
def test_dae_raises_on_codeless_or_nonjson_stdout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, stdout: str
) -> None:
    """A --json stdout with no parseable ``code`` is a hard failure, not silent None."""
    _patch_run(monkeypatch, stdout=stdout)
    with pytest.raises(AssertionError):
        _journey._dae(tmp_path, "lab", "visualize")


def test_dae_returns_the_code_on_a_valid_envelope(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A well-formed --json envelope yields (exit, code, stdout) unchanged."""
    stdout = '{"code": "dae.lab.visualize.ok", "status": "ok"}'
    _patch_run(monkeypatch, stdout=stdout, returncode=0)
    assert _journey._dae(tmp_path, "lab", "visualize") == (
        0,
        "dae.lab.visualize.ok",
        stdout,
    )
