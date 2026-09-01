"""Shared helpers for the ``test_copy_layout*`` suites; not collected."""

from __future__ import annotations

from pathlib import Path

from tests._helpers import _copy_lab, _run_once_dirs
from tests._helpers import (
    _daedalus as _daedalus_dir,
)

# ``_copy_lab``/``_run_once_dirs`` and ``_daedalus`` (kept under its legacy
# ``_daedalus_dir`` name here) were hoisted to tests._helpers and are
# re-exported (``__all__``) for the suites importing them from this module.
__all__ = [
    "_copy_lab",
    "_daedalus_dir",
    "_data_paths",
    "_manifest_dirs",
    "_run",
    "_run_once_dirs",
]


def _run(lab: Path, lab_name: str):
    """Run a copied lab under LocalEngine; return (result, flow_dir)."""
    from daedalus.core.engine import LabConfig, LocalEngine
    from daedalus.core.recipe import build_plan, load_recipe

    spec = load_recipe(lab / "lab.yaml")
    plan = build_plan(spec, lab)
    config = LabConfig(
        lab_name=lab_name,
        lab_dir=lab,
        seed=0,
        output_root=lab / "dae-outputs",
    )
    result = LocalEngine().execute_dag(plan, config=config)
    flows = sorted(p for p in (lab / "dae-outputs" / "flows").iterdir() if p.is_dir())
    assert len(flows) == 1, f"expected one flow, found {flows}"
    return result, flows[0]


def _data_paths(flow: Path) -> list[str]:
    """Sorted relative paths of every non-dae-* leaf file under the flow."""
    return sorted(
        p.relative_to(flow).as_posix()
        for p in flow.rglob("*")
        if p.is_file() and not p.name.startswith("dae-")
    )


def _manifest_dirs(flow: Path) -> list[str]:
    """Sorted relative dirs under the flow that carry a dae-manifest.json."""
    return sorted(
        p.parent.relative_to(flow).as_posix() for p in flow.rglob("dae-manifest.json")
    )
