"""Per fixture shape, the walk lines, the validate-then-run chain and the runtime tree.

Shared goldens and helpers live in tests/core/_walk_shapes.py.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.core._walk_shapes import _TREES, _WALK_LINES, _copy_lab, _plan, _run_cli_in

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.integration  # validates and runs the engine over 23 shapes

_RUNNABLE = sorted(_WALK_LINES)


def _flow_dir_tree(lab_copy: Path) -> list[str]:
    """Sorted relative dir paths under the single flow, dae-* entries stripped."""
    flows = lab_copy / "dae-outputs" / "flows"
    flow = next(flows.iterdir())
    out: list[str] = []
    for child in flow.rglob("*"):
        if not child.is_dir():
            continue
        rel = child.relative_to(flow)
        if any(seg.startswith("dae-") for seg in rel.parts):
            continue
        out.append(rel.as_posix())
    return sorted(out)


@pytest.mark.parametrize("name", _RUNNABLE)
def test_walk_lines(name: str) -> None:
    """The Full:/Walks: block is byte-exact (CLI == --json walk_lines)."""
    assert _plan(name).walk_lines() == _WALK_LINES[name]


@pytest.mark.parametrize("name", _RUNNABLE)
def test_validate_then_run_chain(name: str, tmp_path: Path) -> None:
    """The run must also leave a non-empty flow tree, not only return ok."""
    copy = _copy_lab(name, tmp_path)
    assert _run_cli_in(copy, "lab", "validate") == (0, "dae.lab.validate.ok")
    assert _run_cli_in(copy, "lab", "run") == (0, "dae.lab.run.ok")
    assert _flow_dir_tree(copy), "lab.run.ok but the flow tree is empty"


@pytest.mark.parametrize("name", _RUNNABLE)
def test_runtime_tree(name: str, tmp_path: Path) -> None:
    """The nested self-contained walks/walk_J/ copy tree matches the golden."""
    copy = _copy_lab(name, tmp_path)
    assert _run_cli_in(copy, "lab", "run") == (0, "dae.lab.run.ok")
    assert tuple(_flow_dir_tree(copy)) == _TREES[name]
