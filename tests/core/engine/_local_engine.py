"""Shared helpers for the engine suites; not collected.

The bounded-parallel and isolation suites import from here too.
"""

from __future__ import annotations

from pathlib import Path

from tests._helpers import _copy_lab, _daedalus, _run_once_dirs

# _copy_lab, _daedalus and _run_once_dirs moved to tests._helpers; the re-export in
# __all__ keeps the suites' import path stable.
__all__ = [
    "_build_run_plan_for_test",
    "_copy_diamond_join",
    "_copy_lab",
    "_daedalus",
    "_flows_root",
    "_only_flow",
    "_rel_dirs",
    "_run_linear_smoke",
    "_run_once_dirs",
]


def _flows_root(lab: Path) -> Path:
    return lab / "dae-outputs" / "flows"


def _only_flow(lab: Path) -> Path:
    flows = sorted(p for p in _flows_root(lab).iterdir() if p.is_dir())
    assert len(flows) == 1, f"expected exactly one flow, found {flows}"
    return flows[0]


def _copy_diamond_join(tmp_path: Path):
    """Copy diamond_join to tmp_path and build its (plan, config, lab)."""
    from daedalus.core.engine import LabConfig
    from daedalus.core.recipe import build_plan, load_recipe

    lab = _copy_lab("diamond_join", tmp_path)
    spec = load_recipe(lab / "lab.yaml")
    plan = build_plan(spec, lab)
    config = LabConfig(
        lab_name="diamond_join",
        lab_dir=lab,
        seed=0,
        output_root=lab / "dae-outputs",
    )
    return plan, config, lab


def _run_linear_smoke(tmp_path: Path):
    """Copy linear_smoke to tmp_path and run it under LocalEngine; (result, lab)."""
    from daedalus.core.engine import LabConfig, LocalEngine
    from daedalus.core.recipe import build_plan, load_recipe

    lab = _copy_lab("linear_smoke", tmp_path)
    spec = load_recipe(lab / "lab.yaml")
    plan = build_plan(spec, lab)
    config = LabConfig(
        lab_name="linear_smoke",
        lab_dir=lab,
        seed=0,
        output_root=lab / "dae-outputs",
    )
    result = LocalEngine().execute_dag(plan, config=config)
    return result, lab


def _rel_dirs(flow: Path) -> list[str]:
    """Sorted relative paths of the step dirs under flow that carry a manifest."""
    return sorted(
        str(p.parent.relative_to(flow).as_posix())
        for p in flow.rglob("dae-manifest.json")
    )


def _build_run_plan_for_test(lab_dir: Path):
    """Re-derive the _RunPlan of the latest flow under lab_dir for introspection."""
    from daedalus.core import recipe, walks
    from daedalus.core.engine import LabConfig
    from daedalus.core.engine.local import LocalEngine

    spec = recipe.load_recipe(lab_dir / "lab.yaml")
    plan = recipe.build_plan(spec, lab_dir)
    propagated = walks.propagate(spec, lab_dir)
    if isinstance(propagated, walks.WalkDefect):  # pragma: no cover (test labs valid)
        msg = f"propagate refused a test lab: {propagated.token}"
        raise RuntimeError(msg)
    flows_root = lab_dir / "dae-outputs" / "flows"
    flow_dir = sorted(p for p in flows_root.iterdir() if p.is_dir())[-1]
    config = LabConfig(
        lab_name=spec.name or lab_dir.name,
        lab_dir=lab_dir,
        seed=0,
        output_root=lab_dir / "dae-outputs",
    )
    return LocalEngine._build_run_plan(flow_dir, config, propagated, plan)
