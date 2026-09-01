"""The complex multi-region example end to end through the installed ``dae``.

complex is the one example whose 48 config walks differ from its token set.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from tests.journey._journey import _copy_fixture_lab, _dae, _only_flow, _scaffold

pytestmark = pytest.mark.e2e


# A user-facing walk is a configuration: one complete source-to-sink path, one
# choice per brancher and per sibling-collector set. complex is multi-region,
# so its 48 config walks differ from its token set; this pins the whole block.
_COMPLEX_CONFIG_WALK_LINES = [
    "Full:  1-2-{3-{5,6-10,7-11-{12,13}-(14)}-(16),4-{8,9-15}-(17)}-(18)"
    "-19-{20,21}-22-(23)-24-{25,26}-{(27),(28)}-[29]-30",
    "Walks: 48",
    "  walk_1: 1-2-3-5-(16)-(18)-19-20-22-(23)-24-25-(27)-[29]-30",
    "  walk_2: 1-2-3-5-(16)-(18)-19-20-22-(23)-24-25-(28)-[29]-30",
    "  walk_3: 1-2-3-5-(16)-(18)-19-20-22-(23)-24-26-(27)-[29]-30",
    "  walk_4: 1-2-3-5-(16)-(18)-19-20-22-(23)-24-26-(28)-[29]-30",
    "  walk_5: 1-2-3-5-(16)-(18)-19-21-22-(23)-24-25-(27)-[29]-30",
    "  walk_6: 1-2-3-5-(16)-(18)-19-21-22-(23)-24-25-(28)-[29]-30",
    "  walk_7: 1-2-3-5-(16)-(18)-19-21-22-(23)-24-26-(27)-[29]-30",
    "  walk_8: 1-2-3-5-(16)-(18)-19-21-22-(23)-24-26-(28)-[29]-30",
    "  walk_9: 1-2-3-6-10-(16)-(18)-19-20-22-(23)-24-25-(27)-[29]-30",
    "  walk_10: 1-2-3-6-10-(16)-(18)-19-20-22-(23)-24-25-(28)-[29]-30",
    "  walk_11: 1-2-3-6-10-(16)-(18)-19-20-22-(23)-24-26-(27)-[29]-30",
    "  walk_12: 1-2-3-6-10-(16)-(18)-19-20-22-(23)-24-26-(28)-[29]-30",
    "  walk_13: 1-2-3-6-10-(16)-(18)-19-21-22-(23)-24-25-(27)-[29]-30",
    "  walk_14: 1-2-3-6-10-(16)-(18)-19-21-22-(23)-24-25-(28)-[29]-30",
    "  walk_15: 1-2-3-6-10-(16)-(18)-19-21-22-(23)-24-26-(27)-[29]-30",
    "  walk_16: 1-2-3-6-10-(16)-(18)-19-21-22-(23)-24-26-(28)-[29]-30",
    "  walk_17: 1-2-3-7-11-12-(14)-(16)-(18)-19-20-22-(23)-24-25-(27)-[29]-30",
    "  walk_18: 1-2-3-7-11-12-(14)-(16)-(18)-19-20-22-(23)-24-25-(28)-[29]-30",
    "  walk_19: 1-2-3-7-11-12-(14)-(16)-(18)-19-20-22-(23)-24-26-(27)-[29]-30",
    "  walk_20: 1-2-3-7-11-12-(14)-(16)-(18)-19-20-22-(23)-24-26-(28)-[29]-30",
    "  walk_21: 1-2-3-7-11-12-(14)-(16)-(18)-19-21-22-(23)-24-25-(27)-[29]-30",
    "  walk_22: 1-2-3-7-11-12-(14)-(16)-(18)-19-21-22-(23)-24-25-(28)-[29]-30",
    "  walk_23: 1-2-3-7-11-12-(14)-(16)-(18)-19-21-22-(23)-24-26-(27)-[29]-30",
    "  walk_24: 1-2-3-7-11-12-(14)-(16)-(18)-19-21-22-(23)-24-26-(28)-[29]-30",
    "  walk_25: 1-2-3-7-11-13-(14)-(16)-(18)-19-20-22-(23)-24-25-(27)-[29]-30",
    "  walk_26: 1-2-3-7-11-13-(14)-(16)-(18)-19-20-22-(23)-24-25-(28)-[29]-30",
    "  walk_27: 1-2-3-7-11-13-(14)-(16)-(18)-19-20-22-(23)-24-26-(27)-[29]-30",
    "  walk_28: 1-2-3-7-11-13-(14)-(16)-(18)-19-20-22-(23)-24-26-(28)-[29]-30",
    "  walk_29: 1-2-3-7-11-13-(14)-(16)-(18)-19-21-22-(23)-24-25-(27)-[29]-30",
    "  walk_30: 1-2-3-7-11-13-(14)-(16)-(18)-19-21-22-(23)-24-25-(28)-[29]-30",
    "  walk_31: 1-2-3-7-11-13-(14)-(16)-(18)-19-21-22-(23)-24-26-(27)-[29]-30",
    "  walk_32: 1-2-3-7-11-13-(14)-(16)-(18)-19-21-22-(23)-24-26-(28)-[29]-30",
    "  walk_33: 1-2-4-8-(17)-(18)-19-20-22-(23)-24-25-(27)-[29]-30",
    "  walk_34: 1-2-4-8-(17)-(18)-19-20-22-(23)-24-25-(28)-[29]-30",
    "  walk_35: 1-2-4-8-(17)-(18)-19-20-22-(23)-24-26-(27)-[29]-30",
    "  walk_36: 1-2-4-8-(17)-(18)-19-20-22-(23)-24-26-(28)-[29]-30",
    "  walk_37: 1-2-4-8-(17)-(18)-19-21-22-(23)-24-25-(27)-[29]-30",
    "  walk_38: 1-2-4-8-(17)-(18)-19-21-22-(23)-24-25-(28)-[29]-30",
    "  walk_39: 1-2-4-8-(17)-(18)-19-21-22-(23)-24-26-(27)-[29]-30",
    "  walk_40: 1-2-4-8-(17)-(18)-19-21-22-(23)-24-26-(28)-[29]-30",
    "  walk_41: 1-2-4-9-15-(17)-(18)-19-20-22-(23)-24-25-(27)-[29]-30",
    "  walk_42: 1-2-4-9-15-(17)-(18)-19-20-22-(23)-24-25-(28)-[29]-30",
    "  walk_43: 1-2-4-9-15-(17)-(18)-19-20-22-(23)-24-26-(27)-[29]-30",
    "  walk_44: 1-2-4-9-15-(17)-(18)-19-20-22-(23)-24-26-(28)-[29]-30",
    "  walk_45: 1-2-4-9-15-(17)-(18)-19-21-22-(23)-24-25-(27)-[29]-30",
    "  walk_46: 1-2-4-9-15-(17)-(18)-19-21-22-(23)-24-25-(28)-[29]-30",
    "  walk_47: 1-2-4-9-15-(17)-(18)-19-21-22-(23)-24-26-(27)-[29]-30",
    "  walk_48: 1-2-4-9-15-(17)-(18)-19-21-22-(23)-24-26-(28)-[29]-30",
]


def test_complex_visualize_pins_the_full_config_block_through_binary(
    tmp_path: Path,
) -> None:
    """The fixture's module_A..module_AD ids keep the integer labels stable."""
    lab = _copy_fixture_lab("complex", tmp_path)

    vexit, vcode, vstdout = _dae(lab, "lab", "visualize")
    assert (vexit, vcode) == (0, "dae.lab.visualize.ok"), vstdout
    payload = json.loads(vstdout)["data"]
    # walk_lines is the user-facing configuration view.
    assert payload["walk_lines"] == _COMPLEX_CONFIG_WALK_LINES, vstdout
    # the config view and the token-set view are both emitted, and differ.
    assert payload["walk_lines"] != payload["token_walk_lines"], vstdout


# Each unique instance runs once under .daedalus/<token>/ with its manifest;
# every config walk dir is a manifest-free copy. The checks below derive from
# the tree: 48 config dirs, none empty, no manifest in a copy, store < copies.
_COMPLEX_CONFIG_DIR_COUNT = 48


def _config_walk_dirs(flow: Path) -> list[Path]:
    """The walk_J dirs under a flow; the layout is a literal, not a core import."""
    return sorted(p for p in flow.rglob("walks/walk_*") if p.is_dir())


def _copy_step_dirs(flow: Path) -> list[Path]:
    """Every NN_module step copy dir under any config walk dir."""
    nn_module = re.compile(r"^\d\d_")
    return sorted(
        d
        for w in _config_walk_dirs(flow)
        for d in w.iterdir()
        if d.is_dir() and nn_module.match(d.name)
    )


def test_complex_run_materializes_the_48_config_tree_through_binary(
    tmp_path: Path,
) -> None:
    """The journey row checks final/ only; this pins the materialized copy tree."""
    _scaffold(tmp_path, "complex")
    lab = tmp_path / "complex"
    assert _dae(lab, "lab", "run")[:2] == (0, "dae.lab.run.ok")

    flow = _only_flow(lab)
    config_dirs = _config_walk_dirs(flow)
    assert len(config_dirs) == _COMPLEX_CONFIG_DIR_COUNT, (
        f"expected {_COMPLEX_CONFIG_DIR_COUNT} config walks, got "
        f"{sorted(p.name for p in config_dirs)}"
    )
    # the config dirs are 1..48 with no gap (per-configuration index order).
    assert sorted(p.name for p in config_dirs) == sorted(
        f"walk_{j}" for j in range(1, _COMPLEX_CONFIG_DIR_COUNT + 1)
    )

    copy_dirs = _copy_step_dirs(flow)
    # copies exist and no config dir is empty, so the manifest-free check below
    # cannot pass vacuously.
    assert copy_dirs, "no config-walk step copies were materialized"
    assert all(any(d.parent == w for d in copy_dirs) for w in config_dirs), (
        "a config walk dir materialized no step copies"
    )
    # no copy carries a manifest; the records stay in .daedalus/.
    assert not any((d / "dae-manifest.json").exists() for d in copy_dirs), (
        "a config-walk copy leaked a dae-manifest.json (self-containment broken)"
    )

    # the run-once store deduplicated the config copies: one manifest per unique
    # instance, strictly fewer than the copies.
    store = lab / ".daedalus"
    store_manifests = sorted(store.rglob("dae-manifest.json"))
    assert store_manifests, "the run-once store wrote no manifests"
    assert len(store_manifests) < len(copy_dirs), (
        "the run-once store did not deduplicate the config copies"
    )
