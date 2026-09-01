"""Per-flight final/ holds the union of a flight's sibling walk-collector outputs.

Its flight_collector reads a.json, b.json and c.json from each flight's final/.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from daedalus.core.engine.local import _copy_merged
from tests._helpers import _copy_lab, _run_cli_in
from tests.core.engine._local_engine import _only_flow

pytestmark = pytest.mark.integration

LAB = "flight_final_merge"
LAB_M2 = "flight_final_merge_m2"
_SIBLING_FILES = {"a.json", "b.json", "c.json"}
# Flight number to user-facing label; the m2 emitter writes a length-2 roster.
# The test owns this mapping and never reads it back from engine output.
_M2_FLIGHT_LABEL = {1: "flight_1", 2: "flight_2"}


def test_run_completes_when_flight_collector_reads_all_siblings(tmp_path: Path) -> None:
    """fc raises on a dropped sibling, so a clean run proves the final/ merge."""
    copy = _copy_lab(LAB, tmp_path)
    assert _run_cli_in(copy, "lab", "run") == (0, "dae.lab.run.ok")


def test_flight_final_holds_the_union_of_sibling_collectors(tmp_path: Path) -> None:
    copy = _copy_lab(LAB, tmp_path)
    assert _run_cli_in(copy, "lab", "run") == (0, "dae.lab.run.ok")
    final = _only_flow(copy) / "flights" / "flight_1" / "final"
    names = {p.name for p in final.iterdir()}
    assert names == _SIBLING_FILES, (
        f"flight_1/final/ should be the union {_SIBLING_FILES}, got {names}"
    )


def _src_with(parent: Path, name: str, *files: str) -> Path:
    """A source dir under ``parent`` holding the given (empty) files."""
    src = parent / name
    src.mkdir()
    for f in files:
        (src / f).write_text("{}\n")
    return src


def test_copy_merged_unions_distinct_files(tmp_path: Path) -> None:
    """_copy_merged stages the union of distinct-named sources into dst."""
    a = _src_with(tmp_path, "a", "a.json")
    b = _src_with(tmp_path, "b", "b.json")
    dst = tmp_path / "final"

    _copy_merged([a, b], dst)

    assert {p.name for p in dst.iterdir()} == {"a.json", "b.json"}


def test_copy_merged_is_last_writer_wins_on_same_name(tmp_path: Path) -> None:
    """Last writer wins, matching the pre-merge single-tail copy."""
    a = _src_with(tmp_path, "a", "dup.json")
    (a / "dup.json").write_text('{"from": "a"}\n')
    b = _src_with(tmp_path, "b", "dup.json")
    (b / "dup.json").write_text('{"from": "b"}\n')
    dst = tmp_path / "final"

    _copy_merged([a, b], dst)

    assert {p.name for p in dst.iterdir()} == {"dup.json"}
    assert json.loads((dst / "dup.json").read_text()) == {"from": "b"}


def _any_fc_combined(flow: Path) -> dict[str, object]:
    """fc's combined.json; root scope, so every walk copy holds the same bytes."""
    combined = sorted(flow.rglob("05_fc/combined.json"))
    assert combined, "fc never produced combined.json"
    parsed = json.loads(combined[0].read_text())
    assert isinstance(parsed, dict)
    return parsed


def test_flight_final_isolation_at_m2(tmp_path: Path) -> None:
    """Each flight_K/final/ holds only its own a/b/c.json, each labeled flight_K."""
    copy = _copy_lab(LAB_M2, tmp_path)
    assert _run_cli_in(copy, "lab", "run") == (0, "dae.lab.run.ok")
    flow = _only_flow(copy)
    for k, label in _M2_FLIGHT_LABEL.items():
        final = flow / "flights" / f"flight_{k}" / "final"
        names = {p.name for p in final.iterdir()}
        assert names == _SIBLING_FILES, (
            f"flight_{k}/final/ should be the union {_SIBLING_FILES}, got {names}"
        )
        for name in _SIBLING_FILES:
            got = json.loads((final / name).read_text())["flight"]
            assert got == label, (
                f"flight_{k}/final/{name} carries {got!r}, expected {label!r} "
                f"(a cross-flight k-swap in the per-flight final/ merge)"
            )


def test_m2_flight_collector_reads_its_own_final(tmp_path: Path) -> None:
    """combined[flight_K] carries only the flight_K label in all three files."""
    copy = _copy_lab(LAB_M2, tmp_path)
    assert _run_cli_in(copy, "lab", "run") == (0, "dae.lab.run.ok")
    combined = _any_fc_combined(_only_flow(copy))
    assert set(combined) == set(_M2_FLIGHT_LABEL.values()), (
        f"fc combined keys {sorted(combined)} != flights {_M2_FLIGHT_LABEL}"
    )
    for label in _M2_FLIGHT_LABEL.values():
        flight_block = combined[label]
        assert isinstance(flight_block, dict)
        labels = {entry["flight"] for entry in flight_block.values()}
        assert labels == {label}, (
            f"fc combined[{label!r}] mixes flights {labels}; expected {{{label!r}}}"
        )
