"""daedalus.flow public API - Role, FlowContext, and the @entry decorator.

This single module holds the entire surface a daedalus module author needs.
``daedalus.flow.__init__`` re-exports the three public names below; nothing
outside this package reaches into the module directly. Read top to bottom:
``Role`` (the role vocabulary), ``FlowContext`` (the object handed to every
module), then ``entry`` (the decorator that marks a module's entry point).
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path


class Role(StrEnum):
    """The four module roles, a closed set; a module reads its own as ``ctx.role``."""

    EMITTER = "emitter"  # declares the targets, one Flight per target
    TRANSFORM = "transform"  # reads one input dir, writes one output dir
    WALK_COLLECTOR = "walk_collector"  # converges the Walks inside one Flight
    FLIGHT_COLLECTOR = "flight_collector"  # converges results across all Flights


@dataclass(frozen=True)
class FlowContext:
    """The runtime context daedalus passes to a module's entry function."""

    # Which step this is and what role it plays. Every field is always set; a
    # field that does not apply to the role holds an empty default, not None.
    step_id: str  # this module's own id in the Lab recipe
    role: Role  # this module's role (always set)

    # The only two paths your module needs. daedalus creates the output
    # directory for you before the call; just read from one and write to the
    # other.
    step_input_path: Path  # upstream output dir (the Lab's inputs/ at the root)
    step_output_path: Path  # where to write this step's results (pre-created)

    # Which Flight (target) and Walk (method) this invocation belongs to.
    # Both are 1-indexed and always set; a plain step outside any fan-out sees
    # the defaults below.
    flight_id: str = "flight_1"
    walk_id: str = "walk_1"

    # Aggregation inputs. These map an upstream id to its output directory and
    # are filled in only for the aggregator roles; every other module sees an
    # empty dict.
    walk_inputs: dict[str, Path] = field(default_factory=dict)  # walk_id -> dir
    flight_inputs: dict[str, Path] = field(default_factory=dict)  # flight_id -> dir

    # A deterministic seed, derived from (flight_id, walk_id, step_id), so two
    # runs of the same step draw the same random numbers.
    seed: int = 0


# A module entry point takes the run context, writes its outputs, returns None.
ModuleEntry = Callable[[FlowContext], None]


def entry(func: ModuleEntry) -> ModuleEntry:
    """Mark ``func`` as a module's entry point.

    Decorate one function per module with ``@dae.entry``; it takes a single
    :class:`FlowContext` and writes its results into ``ctx.step_output_path``.
    The decorator only tags the function for discovery.
    """
    # The discovery marker is a dynamic attribute on the user's function
    # object, which Callable does not model; hence the type-ignore.
    func.__daedalus_entry__ = True  # type: ignore[attr-defined]
    return func
