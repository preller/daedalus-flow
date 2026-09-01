"""IO and persistence tests for the lineage record, atomic writes and flow ids.

Stdlib-only JSON, all writes to tmp_path; the schema half is in test_lineage.py.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from daedalus.core import lineage
from daedalus.core.lineage import _io


def test_atomic_write_leaves_no_tmp_file(tmp_path: Path) -> None:
    """The atomic write replaces in place and leaves no ``.tmp`` sibling behind."""
    manifest = lineage.StepManifest(step_id="x", status="running", seed=1)
    lineage.write_step_manifest(tmp_path, manifest)
    names = sorted(p.name for p in tmp_path.iterdir())
    assert names == [lineage.STEP_MANIFEST_NAME]


def test_write_flow_outputs_excludes_reserved_prefix(tmp_path: Path) -> None:
    """The exclusion keys on the reserved dae- prefix, not the manifest name."""
    flow_dir = tmp_path / "flow"
    step_dir = flow_dir / "05_collect_report"
    (step_dir / "sub").mkdir(parents=True)
    (step_dir / "dae-manifest.json").write_text("{}")
    (step_dir / "run_report.json").write_text('{"ok": true}')
    (step_dir / "sub" / "b.json").write_text('{"n": 1}')

    out = lineage.write_flow_outputs(flow_dir, step_dir)

    assert out == flow_dir / "output"
    names = {p.name for p in out.rglob("*")}
    assert "dae-manifest.json" not in names
    assert (out / "run_report.json").read_text() == '{"ok": true}'
    assert (out / "sub" / "b.json").read_text() == '{"n": 1}'


def test_write_flow_outputs_leaves_no_tmp(tmp_path: Path) -> None:
    """No ``output.tmp`` sibling remains after the copy."""
    flow_dir = tmp_path / "flow"
    step_dir = flow_dir / "01_x"
    step_dir.mkdir(parents=True)
    (step_dir / "dae-manifest.json").write_text("{}")
    (step_dir / "a.json").write_text("1")

    lineage.write_flow_outputs(flow_dir, step_dir)

    names = sorted(p.name for p in flow_dir.iterdir())
    assert "output.tmp" not in names
    assert "output" in names


def test_write_flow_outputs_replaces_stale(tmp_path: Path) -> None:
    """A pre-existing ``output/`` is fully replaced, not merged (re-entrancy safe)."""
    flow_dir = tmp_path / "flow"
    step_dir = flow_dir / "01_x"
    step_dir.mkdir(parents=True)
    (step_dir / "dae-manifest.json").write_text("{}")
    (step_dir / "new.json").write_text("new")
    stale = flow_dir / "output"
    stale.mkdir()
    (stale / "old.json").write_text("old")

    lineage.write_flow_outputs(flow_dir, step_dir)

    out = flow_dir / "output"
    assert (out / "new.json").exists()
    assert not (out / "old.json").exists()


def test_write_flow_outputs_empty_source_yields_empty_dir(tmp_path: Path) -> None:
    """output/ is the completed-with-results signal, so it exists even when empty."""
    flow_dir = tmp_path / "flow"
    step_dir = flow_dir / "01_x"
    step_dir.mkdir(parents=True)
    (step_dir / "dae-manifest.json").write_text("{}")

    out = lineage.write_flow_outputs(flow_dir, step_dir)

    assert out.is_dir()
    assert list(out.iterdir()) == []


def test_list_flows_empty_when_no_flows_dir(tmp_path: Path) -> None:
    """list_flows on a root with no flows/ dir is the empty list (valid query)."""
    assert lineage.list_flows(tmp_path) == []


def test_list_flows_sorts_by_parsed_key_not_raw_string(tmp_path: Path) -> None:
    """A raw string sort would put ..._10 before ..._2."""
    flows_root = tmp_path / "flows"
    flows_root.mkdir()
    expected = [
        "flow_20260611_073200",
        "flow_20260611_073200_2",
        "flow_20260611_073200_10",
        "flow_20260611_073201",
    ]
    # create them out of order
    creation_order = [expected[2], expected[0], expected[3], expected[1]]
    for flow_id in creation_order:
        (flows_root / flow_id).mkdir()

    assert lineage.list_flows(tmp_path) == expected
    # the latest by parsed key is the next-second flow, not the raw-string max
    assert lineage.list_flows(tmp_path)[-1] == "flow_20260611_073201"


def test_new_flow_id_base_when_no_collision() -> None:
    """new_flow_id with no clash returns the bare ``flow_<YYYYMMDD>_<HHMMSS>``."""
    now = datetime(2026, 6, 11, 7, 32, 0, tzinfo=UTC)
    assert lineage.new_flow_id(now, existing=[]) == "flow_20260611_073200"


def test_new_flow_id_suffixes_on_same_second_collision() -> None:
    """A same-second clash gets the next ``_<n>`` suffix (n >= 2)."""
    now = datetime(2026, 6, 11, 7, 32, 0, tzinfo=UTC)
    one_taken = ["flow_20260611_073200"]
    assert lineage.new_flow_id(now, one_taken) == "flow_20260611_073200_2"

    two_taken = ["flow_20260611_073200", "flow_20260611_073200_2"]
    assert lineage.new_flow_id(now, two_taken) == "flow_20260611_073200_3"


def test_atomic_write_stages_tmp_in_target_parent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A tmp on another filesystem would make os.replace fail across devices."""
    target = tmp_path / "nested" / "dae-flow.json"
    seen: dict[str, Path] = {}
    real_replace = os.replace

    def _spy_replace(src: object, dst: object) -> None:
        seen["tmp"] = Path(str(src))
        real_replace(str(src), str(dst))

    monkeypatch.setattr(os, "replace", _spy_replace)
    _io._atomic_write_json(target, {"format_version": 1, "k": "v"})

    assert seen["tmp"].parent == target.parent


def test_atomic_write_fsyncs_before_replace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The bytes must hit disk before the rename, not only the page cache."""
    order: list[str] = []
    real_fsync = os.fsync
    real_replace = os.replace

    def _spy_fsync(fd: int) -> None:
        order.append("fsync")
        real_fsync(fd)

    def _spy_replace(src: object, dst: object) -> None:
        order.append("replace")
        real_replace(str(src), str(dst))

    monkeypatch.setattr(os, "fsync", _spy_fsync)
    monkeypatch.setattr(os, "replace", _spy_replace)
    _io._atomic_write_json(tmp_path / "dae-flow.json", {"format_version": 1})

    assert order == ["fsync", "replace"]


def test_atomic_write_failure_leaves_prior_file_intact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """os.replace is the only mutation; a failure before it leaves the old bytes."""
    target = tmp_path / "dae-flow.json"
    _io._atomic_write_json(target, {"format_version": 1, "status": "completed"})

    def _boom(*_: object, **__: object) -> None:
        raise OSError("disk full mid-write")

    monkeypatch.setattr(os, "replace", _boom)
    with pytest.raises(OSError, match="disk full"):
        _io._atomic_write_json(target, {"format_version": 1, "status": "running"})

    # The old record is intact and fully parseable, never a half-written file.
    recovered = json.loads(target.read_text())
    assert recovered["status"] == "completed"
