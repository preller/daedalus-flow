"""Walk-model data layer, the public dataclasses, constants and leaf helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

# Max instances per flight before validate refuses.
DEFAULT_WALK_BUDGET = 1024

# Max configuration walks (the cartesian product of decision points) before
# validate refuses. Collectors keep the instance count linear while the
# configuration count grows exponentially, so the two budgets are separate axes.
DEFAULT_CONFIG_BUDGET = 256

# Instance ids are '<module_id>@w<id>'; '@' is therefore banned in module ids
# (walk ids are machine-assigned integers, so injectivity is structural).
_RESERVED_SEPARATOR = "@"

_GLOBAL_ROOT = "w1"
_FLIGHT_ID = "f1"  # M=1: the degenerate flight identity.


class WalkInvariantError(RuntimeError):
    """The arithmetic cross-check diverged from the pass; a bug, not a lab defect."""


@dataclass(frozen=True)
class WalkRecord:
    """One walk's lineage record."""

    walk_id: str
    flight_id: str | None  # ``"f1"`` for flight-scope walks; None for the global root
    parent_walk: str | None  # nesting is recoverable from here; the counter stays flat
    born_at: str | None  # the minting brancher, or the emitter for the flight root
    branch_module: str | None  # the branch edge's successor; None for the flight root


@dataclass(frozen=True)
class Instance:
    """One step instance in G*, ``<module_id>@w<id>`` plus its ``NN`` plan index."""

    instance_id: str
    module_id: str
    walk_id: str
    index: int


@dataclass(frozen=True)
class WalkDefect:
    """A walk-model defect leaf, a token plus a human reason, first defect only."""

    token: str
    reason: str


@dataclass(frozen=True)
class WalkPlan:
    """The propagated walk plan for one lab at M=1."""

    walks: tuple[WalkRecord, ...]  # counter order
    instances: tuple[Instance, ...]  # encounter order; tokens sorted per module
    edges: tuple[tuple[str, str], ...]  # sorted G* edges over instance ids
    walk_inputs: Mapping[str, Mapping[str, str]]  # collector instance -> walk -> tail
    terminal: tuple[str, ...]  # instance ids with no G* successor
    roles: Mapping[str, str]
    config_full: str
    _lines: tuple[str, ...]

    def walk_lines(self) -> tuple[str, ...]:
        """The token-set walk-string block (internal/machine view), ASCII only."""
        return self._lines

    def config_lines(self) -> tuple[str, ...]:
        """The configuration-walk block, the user-facing primary view.

        A ``Full:`` shape line, a ``Walks: <count>`` line, and one line per
        configuration, each a complete source-to-sink path with its collectors
        marked. ``walk_lines`` is the token-set view emitted in ``--json``.
        """
        from daedalus.core.walks._config import _config_lines  # noqa: PLC0415

        return (f"Full:  {self.config_full}", *_config_lines(self))


def _walk_num(walk_id: str) -> int:
    """Numeric sort key for walk ids ('w10' sorts after 'w2')."""
    return int(walk_id[1:])


def _instance_id(module_id: str, walk_id: str) -> str:
    return f"{module_id}{_RESERVED_SEPARATOR}{walk_id}"


def _module_of(instance_id: str) -> str:
    return instance_id.rsplit(_RESERVED_SEPARATOR, 1)[0]


def _walk_of(instance_id: str) -> str:
    return instance_id.rsplit(_RESERVED_SEPARATOR, 1)[1]
