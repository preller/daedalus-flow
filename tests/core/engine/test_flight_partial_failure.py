"""One flight of an M>1 fan-out raises mid-flight; the other flights complete.

The test derives the failing flight from ``input/items.json``, never from engine output.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from daedalus.core import lineage
from daedalus.core.topology import INTERNAL_DIR
from tests._helpers import _copy_lab, _run_cli_in
from tests.core.engine._local_engine import _only_flow

pytestmark = pytest.mark.integration

LAB = "flight_one_fails"
# work raises on this item. The fixture duplicates it; the test never reads it
# back from engine output.
_DOOMED_ITEM = 20


def _flight_dirs(flow: Path) -> list[Path]:
    """The flights/flight_* dirs under a flow (the user-facing partition)."""
    flights = flow / "flights"
    if not flights.is_dir():
        return []
    return sorted(
        p for p in flights.iterdir() if p.is_dir() and p.name.startswith("flight_")
    )


def _items(lab: Path) -> list[object]:
    """The roster literal, read from the fixture's input/items.json."""
    parsed = json.loads((lab / "input" / "items.json").read_text())
    assert isinstance(parsed, list)
    return parsed


def _work_manifests(lab: Path) -> list[lineage.StepManifest]:
    """Every ``work`` StepManifest from the .daedalus run-once store."""
    store = lab / INTERNAL_DIR
    out: list[lineage.StepManifest] = []
    for manifest_path in sorted(store.glob("*/*/dae-manifest.json")):
        manifest = lineage.read_step_manifest(manifest_path.parent)
        if manifest.step_id == "work":
            out.append(manifest)
    return out


def test_mid_flight_failure_reports_failed_outcome(tmp_path: Path) -> None:
    """A mid-flight RuntimeError surfaces as exit 1 and dae.lab.run.failed."""
    copy = _copy_lab(LAB, tmp_path)
    assert _run_cli_in(copy, "lab", "run") == (1, "dae.lab.run.failed")


def test_failed_flight_is_recorded_in_lineage(tmp_path: Path) -> None:
    """The failed manifest's flight_id is the internal token f{items.index(20) + 1}."""
    copy = _copy_lab(LAB, tmp_path)
    assert _run_cli_in(copy, "lab", "run") == (1, "dae.lab.run.failed")

    failing_index = _items(copy).index(_DOOMED_ITEM)
    expected_token = f"f{failing_index + 1}"

    manifests = _work_manifests(copy)
    failed = [m for m in manifests if m.status == "failed"]
    statuses = [m.status for m in manifests]
    assert len(failed) == 1, (
        f"expected exactly one failed work manifest, got {statuses}"
    )
    assert failed[0].flight_id == expected_token, (
        f"failed work flight_id {failed[0].flight_id!r} != internal token "
        f"{expected_token!r} (items.index({_DOOMED_ITEM}) + 1)"
    )


def test_failed_run_writes_no_user_flights_tree(tmp_path: Path) -> None:
    """A failed run writes no flights/ or final/; survivors stay in .daedalus/."""
    # flights/ is materialized right before the flight_collector runs; a stranded
    # flight keeps the collector unready, so neither flights/ nor final/ appears.
    # TODO: materialize the surviving flights' user view on a failed run.
    copy = _copy_lab(LAB, tmp_path)
    assert _run_cli_in(copy, "lab", "run") == (1, "dae.lab.run.failed")
    flow = _only_flow(copy)

    assert not (flow / "flights").exists(), "a failed run must not write flights/"
    assert not (flow / "final").exists(), "a failed run must not write final/"
    assert _flight_dirs(flow) == []

    # At least one work instance outside the doomed flight completed and kept its
    # picked.json in the run-once store.
    survivors = [m for m in _work_manifests(copy) if m.status == "completed"]
    assert survivors, "expected at least one surviving (completed) work instance"
    store = copy / INTERNAL_DIR
    survivor_outputs = [
        p for token_dir in store.iterdir() for p in token_dir.glob("*_work/picked.json")
    ]
    assert survivor_outputs, "surviving work output (picked.json) missing from store"


def test_all_flights_fail_is_a_clean_failed_run(tmp_path: Path) -> None:
    """With every flight doomed the run is still (1, failed) and writes no flights/."""
    copy = _copy_lab(LAB, tmp_path)
    (copy / "input" / "items.json").write_text(
        json.dumps([_DOOMED_ITEM, _DOOMED_ITEM, _DOOMED_ITEM]) + "\n"
    )
    assert _run_cli_in(copy, "lab", "run") == (1, "dae.lab.run.failed")
    flow = _only_flow(copy)
    assert not (flow / "flights").exists()
    assert _flight_dirs(flow) == []
