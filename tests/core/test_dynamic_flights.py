"""M>1 fan-out, one flight per emitter item, checked as a bijection.

Expected M is len(input/items.json) of the fixture, never an engine output.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests._helpers import _copy_lab, _run_cli_in, fixtures_root
from tests.core.engine._local_engine import _only_flow

_FIXTURE_LABS = fixtures_root() / "labs"

pytestmark = pytest.mark.integration  # runs the engine over the M>1 fixtures

# emitter_range5 (M=5), emitter_list_abc (M=3, non-integer items) and emitter_range1
# (M=1, the regression case) share the bijection asserts. emitter_range0 (M=0) is its
# own edge test, since an empty partition has no flights to count.
_FANOUT = ["emitter_range5", "emitter_list_abc", "emitter_range1"]


def _items(name: str) -> list[object]:
    """The emitter literal, read from the fixture's input/items.json."""
    return json.loads((_FIXTURE_LABS / name / "input" / "items.json").read_text())


def _expected_m(name: str) -> int:
    """M, the length of the emitter literal."""
    return len(_items(name))


def _flight_dirs(flow: Path) -> list[Path]:
    """The flights/flight_* dirs under a flow (the user-facing partition)."""
    flights = flow / "flights"
    if not flights.is_dir():
        return []
    return sorted(
        p for p in flights.iterdir() if p.is_dir() and p.name.startswith("flight_")
    )


def _flight_items(flow: Path) -> dict[str, list[object]]:
    """Per flight dir name, the items its ``work`` step recorded in picked.json."""
    out: dict[str, list[object]] = {}
    for flight in _flight_dirs(flow):
        # Read only the per-flight walk copy, not the per-flight final/ mirror. The
        # tree keeps a byte copy of the flight terminal in both, so counting the whole
        # subtree would double every item.
        items = [
            json.loads(p.read_text())["item"]
            for p in sorted((flight / "walks").rglob("picked.json"))
        ]
        out[flight.name] = items
    return out


def _sorted_json(items: list[object]) -> list[object]:
    """Stable order for a homogeneous item multiset (matches gather's key)."""
    return sorted(items, key=lambda x: json.dumps(x, sort_keys=True))


@pytest.mark.parametrize("name", [*_FANOUT, "emitter_range0"])
def test_items_json_is_a_list_and_m_is_its_length(name: str) -> None:
    """items.json is a list and M is its length; the bijection asserts rest on it."""
    items = _items(name)
    assert isinstance(items, list), f"{name}/input/items.json must be a JSON list"
    assert _expected_m(name) == len(items)


@pytest.mark.parametrize("name", _FANOUT)
def test_flight_count_equals_emitter_partition(name: str, tmp_path: Path) -> None:
    """Flight dirs are flight_1..flight_M with M = len(emitter output)."""
    copy = _copy_lab(name, tmp_path)
    assert _run_cli_in(copy, "lab", "run") == (0, "dae.lab.run.ok")
    flights = _flight_dirs(_only_flow(copy))
    assert [p.name for p in flights] == [
        f"flight_{k}" for k in range(1, _expected_m(name) + 1)
    ], f"{name}: expected {_expected_m(name)} flights, got {[p.name for p in flights]}"


@pytest.mark.parametrize("name", _FANOUT)
def test_each_flight_input_is_a_singleton(name: str, tmp_path: Path) -> None:
    """Each flight's input/ holds exactly one emitter item (bijection assertion 3)."""
    copy = _copy_lab(name, tmp_path)
    assert _run_cli_in(copy, "lab", "run") == (0, "dae.lab.run.ok")
    per_flight = _flight_items(_only_flow(copy))
    assert len(per_flight) == _expected_m(name), per_flight
    for flight, items in per_flight.items():
        assert len(items) == 1, (
            f"{name}/{flight} received a non-singleton input: {items}"
        )


@pytest.mark.parametrize("name", _FANOUT)
def test_flight_inputs_union_equals_emitter_output(name: str, tmp_path: Path) -> None:
    """Checked on the per-flight picked items and on gather's final/gathered.json."""
    copy = _copy_lab(name, tmp_path)
    assert _run_cli_in(copy, "lab", "run") == (0, "dae.lab.run.ok")
    flow = _only_flow(copy)

    emitter_items = _sorted_json(_items(name))
    union = _sorted_json(
        [item for items in _flight_items(flow).values() for item in items]
    )
    assert union == emitter_items, (
        f"{name}: union of flight inputs {union} != emitter {emitter_items}"
    )

    gathered = json.loads((flow / "final" / "gathered.json").read_text())
    assert _sorted_json(gathered) == emitter_items, (
        f"{name}: gather output {gathered} != {emitter_items}"
    )


def test_m0_empty_partition_is_a_successful_zero_flight_run(tmp_path: Path) -> None:
    """emitter_range0 yields []; the run reports ok_empty with no flights/ dir."""
    copy = _copy_lab("emitter_range0", tmp_path)
    assert _run_cli_in(copy, "lab", "run") == (0, "dae.lab.run.ok_empty")
    flow = _only_flow(copy)
    assert _flight_dirs(flow) == [], "an empty partition must produce no flights"
    assert not (flow / "flights").exists(), "M=0 must not create a flights/ dir"


# read_partition_count is the only source of M. The fixtures above reach its fallback
# branches only indirectly. A regression in the "not a single roster, so one flight"
# path would turn any broken emitter into M=1 and mask a failure.


def _partition_count(tmp_path: Path, files: dict[str, object]) -> int:
    """Write each name->json-content into tmp_path, then read M back."""
    from daedalus.core.flights import read_partition_count

    for name, content in files.items():
        (tmp_path / name).write_text(json.dumps(content))
    return read_partition_count(tmp_path)


# Anything but a single list-shaped roster is the degenerate one flight.
_DEGENERATE_TO_ONE_FLIGHT = [
    {"marker.json": {"ok": True}},  # a non-list document, a static emitter
    {"a.json": ["x"], "b.json": ["y"]},  # several files, not a single roster
    {},  # no JSON at all, nothing wrote a roster
]


@pytest.mark.parametrize("files", _DEGENERATE_TO_ONE_FLIGHT)
def test_read_partition_count_non_roster_is_degenerate_one(
    tmp_path: Path, files: dict[str, object]
) -> None:
    assert _partition_count(tmp_path, files) == 1


def test_read_partition_count_roster_length_is_m(tmp_path: Path) -> None:
    roster = ["alpha", "beta", "gamma", "delta", "epsilon"]
    assert _partition_count(tmp_path, {"items.json": roster}) == len(roster)


def test_read_partition_count_empty_list_is_zero_not_one(tmp_path: Path) -> None:
    # An empty roster is M=0 (the ok_empty edge), distinct from a static emitter that
    # never wrote a roster (M=1 above); that is why list and non-list are told apart.
    assert _partition_count(tmp_path, {"items.json": []}) == 0


def test_read_partition_count_ignores_dae_prefixed_files(tmp_path: Path) -> None:
    roster = ["one", "two"]
    files: dict[str, object] = {"items.json": roster, "dae-manifest.json": {"k": "v"}}
    # The dae- file must not count as a second JSON (which would force the degenerate
    # M=1); the roster still wins.
    assert _partition_count(tmp_path, files) == len(roster)
