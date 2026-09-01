"""Shared helpers for the test_dag* suites, not collected.

The fixture-lab roots and the inline module-dir writer.
"""

from __future__ import annotations

from pathlib import Path

from tests._helpers import fixtures_root

_FIXTURE_LABS = fixtures_root() / "labs"
_BROKEN_LABS = fixtures_root() / "broken_labs"


def _write_module(lab_dir: Path, mid: str, role: str) -> None:
    """Write a module dir carrying ``role`` for an inline role-bearing lab."""
    (lab_dir / "modules" / mid).mkdir(parents=True)
    (lab_dir / "modules" / mid / "dae-module.yaml").write_text(f"role: {role}\n")
