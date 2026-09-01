"""Parse a lab recipe and design its execution order.

``lab.yaml`` is loaded with PyYAML ``safe_load`` and hand-validated into the
frozen :class:`RecipeSpec` and :class:`RecipeModule` shapes. The package then
classifies structural defects (``first_defect``), computes a deterministic
``execution_order``, decides linearity, and builds the :class:`ExecutionPlan`
the LocalEngine walks. ``_parse``, ``_validate`` and ``_plan`` sit behind this
re-exporting face; the privates in ``__all__`` are reached by dag.py and tests.
"""

from __future__ import annotations

from daedalus.core.recipe._parse import (
    _EMITTER_TYPE,
    _VALID_ROLES,
    RecipeModule,
    RecipeParseError,
    RecipeSpec,
    _parse_isolation,
    _parse_isolation_pref,
    discover_lab,
    load_recipe,
    load_recipe_text,
    read_module_isolation_pref,
    read_module_role,
)
from daedalus.core.recipe._plan import (
    ExecutionPlan,
    PlanStep,
    build_plan,
)
from daedalus.core.recipe._validate import (
    RecipeCycleError,
    _dangling_dep,
    execution_order,
    first_defect,
    linearity_defect,
)

__all__ = [
    "_EMITTER_TYPE",
    "_VALID_ROLES",
    "_dangling_dep",
    "_parse_isolation",
    "_parse_isolation_pref",
    "ExecutionPlan",
    "PlanStep",
    "RecipeCycleError",
    "RecipeModule",
    "RecipeParseError",
    "RecipeSpec",
    "build_plan",
    "discover_lab",
    "execution_order",
    "first_defect",
    "linearity_defect",
    "load_recipe",
    "load_recipe_text",
    "read_module_isolation_pref",
    "read_module_role",
]
