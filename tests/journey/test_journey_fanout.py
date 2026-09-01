"""Dynamic-flights fan-out (M>1) end to end through the installed ``dae``.

M comes from the shipped input row count, a user-side artifact, not the engine.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.journey._journey import _dae, _only_flow, _scaffold

pytestmark = pytest.mark.e2e


def _flight_dir_names(flow: Path) -> list[str]:
    """Sorted flights/flight_* dir names under a flow; the path is a literal."""
    flights = flow / "flights"
    if not flights.is_dir():
        return []
    return sorted(
        p.name for p in flights.iterdir() if p.is_dir() and p.name.startswith("flight_")
    )


def _csv_row_count(csv_path: Path) -> int:
    """Data rows in a scaffolded input CSV, skipping blank and #-comment lines."""
    import csv

    with csv_path.open(newline="") as fh:
        data = [
            line for line in fh if line.strip() and not line.lstrip().startswith("#")
        ]
    return sum(1 for _ in csv.DictReader(data))


def test_demo_fans_out_one_flight_per_target(tmp_path: Path) -> None:
    """demo ships 3 targets in targets.csv, so a run produces flight_1..flight_3."""
    _scaffold(tmp_path, "demo")
    lab = tmp_path / "demo"
    m = _csv_row_count(lab / "input" / "targets.csv")
    assert m == 3, f"demo is expected to ship 3 targets, found {m}"

    assert _dae(lab, "lab", "run")[:2] == (0, "dae.lab.run.ok")
    flow = _only_flow(lab)
    assert _flight_dir_names(flow) == [f"flight_{k}" for k in range(1, m + 1)]


def test_ensemble_fans_out_one_flight_per_target(tmp_path: Path) -> None:
    """One flight per targets.csv row, and the summary's n_targets equals M."""
    _scaffold(tmp_path, "ensemble")
    lab = tmp_path / "ensemble"
    m = _csv_row_count(lab / "input" / "targets.csv")

    assert _dae(lab, "lab", "run")[:2] == (0, "dae.lab.run.ok")
    flow = _only_flow(lab)
    assert _flight_dir_names(flow) == [f"flight_{k}" for k in range(1, m + 1)]

    summary = json.loads((flow / "final" / "summary.json").read_text())
    assert summary["n_targets"] == m, summary
