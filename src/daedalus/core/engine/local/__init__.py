"""LocalEngine and the private names its subclass and tests reach.

``_engine`` holds :class:`LocalEngine`; ``_instance`` holds the run-once runner,
the per-run wiring and the copy primitives; ``_finalize`` holds the output pass.
The private names are listed in ``__all__`` so each re-export is explicit under
mypy's no-implicit-reexport.
"""

from __future__ import annotations

from daedalus.core.engine.local._engine import LocalEngine
from daedalus.core.engine.local._finalize import _finalize_outputs
from daedalus.core.engine.local._instance import (
    _copy_merged,
    _run_one_instance,
    _RunPlan,
    _RunState,
    _StepOutcome,
)

__all__ = [
    "LocalEngine",
    "_RunPlan",
    "_RunState",
    "_StepOutcome",
    "_copy_merged",
    "_finalize_outputs",
    "_run_one_instance",
]
