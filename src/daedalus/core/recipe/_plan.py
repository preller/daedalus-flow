"""Recipe planning, resolving a validated spec into the ordered ExecutionPlan.

The top layer of the recipe package: the plan-shaped dataclasses
(:class:`PlanStep`, :class:`ExecutionPlan`) and ``build_plan``, which walks the
``execution_order`` from ``_validate``, resolves each module's effective role
(the lab.yaml override or the on-disk ``dae-module.yaml`` role), and refuses an
out-of-set role or a source collector before any lineage is written. Nothing
imports from here; it is the package's sink.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from daedalus.flow import Role

from ._parse import (
    _VALID_ROLES,
    RecipeParseError,
    RecipeSpec,
    read_module_role,
)
from ._validate import execution_order

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True)
class PlanStep:
    """One step in an execution plan."""

    index: int  # 1-based, the ``NN`` in the lineage tree
    module_id: str
    module_dir: Path
    role: str  # effective role, the lab.yaml override or the dae-module.yaml role


@dataclass(frozen=True)
class ExecutionPlan:
    """A frozen, ordered plan the engine walks serially."""

    lab_name: str | None
    steps: tuple[PlanStep, ...]


def build_plan(spec: RecipeSpec, lab_dir: Path) -> ExecutionPlan:
    """Resolve a spec into an ordered :class:`ExecutionPlan`.

    The effective role is the lab.yaml ``role:`` when declared, else the module's
    ``dae-module.yaml`` role. A missing module dir, a missing or out-of-set role,
    or a source collector raises RecipeParseError (``dae.lab.run.invalid``).
    """
    order = execution_order(spec)
    lab_roles = {module.id: module.role for module in spec.modules}
    steps: list[PlanStep] = []
    for index, module_id in enumerate(order, start=1):
        module_dir = lab_dir / "modules" / module_id
        if not module_dir.is_dir():
            raise RecipeParseError(
                f"module '{module_id}' has no directory at {module_dir}."
            )
        lab_role = lab_roles.get(module_id)
        role = lab_role if lab_role is not None else read_module_role(module_dir)
        if role is None:
            raise RecipeParseError(
                f"module '{module_id}' has no role: in its dae-module.yaml "
                "and none declared in lab.yaml."
            )
        if role not in _VALID_ROLES:
            raise RecipeParseError(
                f"module '{module_id}' has an unknown role {role!r}; "
                f"valid roles are {', '.join(sorted(_VALID_ROLES))}."
            )
        steps.append(
            PlanStep(
                index=index,
                module_id=module_id,
                module_dir=module_dir,
                role=role,
            )
        )
    roles_by_id = {s.module_id: s.role for s in steps}
    collector_roles = {Role.WALK_COLLECTOR.value, Role.FLIGHT_COLLECTOR.value}
    for module in spec.modules:
        if not module.depends and roles_by_id[module.id] in collector_roles:
            raise RecipeParseError(
                f"module '{module.id}' is the lab's source (no depends) but its "
                f"role {roles_by_id[module.id]!r} converges upstream outputs; "
                "a collector cannot be the source. The source must be an "
                "emitter or a transform."
            )
    return ExecutionPlan(lab_name=spec.name, steps=tuple(steps))
