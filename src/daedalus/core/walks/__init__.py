"""The static walk data model and propagation pass, the walk model.

This recipe-time layer propagates walk tokens through the DAG and produces a
frozen :class:`WalkPlan` of ``(module, walk-token)`` pairs; runtime flight
fan-out belongs to :mod:`daedalus.core.flights`. ``_shared`` holds the data
model and constants, ``_propagation`` the forward pass, ``_config`` the
rendering, ``_arithmetic`` the cross-check. The privates in ``__all__`` are
reached by the engine, visualize and the walk tests.
"""

from __future__ import annotations

from daedalus.core.walks._arithmetic import (
    _arithmetic_walk_count,
    _branch_successor_count,
    _collector_scalar,
)
from daedalus.core.walks._config import (
    _config_count,
    _render_lines,
    _RenderCtx,
    _walk_lineage,
    configurations,
    user_walk,
)
from daedalus.core.walks._propagation import (
    _broadcast_prefixes,
    _Pass,
    _strict_ancestor_in,
    propagate,
)
from daedalus.core.walks._shared import (
    _RESERVED_SEPARATOR,
    DEFAULT_WALK_BUDGET,
    Instance,
    WalkDefect,
    WalkInvariantError,
    WalkPlan,
    WalkRecord,
    _walk_num,
)

__all__ = [
    "DEFAULT_WALK_BUDGET",
    "Instance",
    "WalkDefect",
    "WalkInvariantError",
    "WalkPlan",
    "WalkRecord",
    "_Pass",
    "_RESERVED_SEPARATOR",
    "_RenderCtx",
    "_arithmetic_walk_count",
    "_branch_successor_count",
    "_broadcast_prefixes",
    "_collector_scalar",
    "_config_count",
    "_render_lines",
    "_strict_ancestor_in",
    "_walk_lineage",
    "_walk_num",
    "configurations",
    "propagate",
    "user_walk",
]
