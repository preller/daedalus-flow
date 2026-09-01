"""The OrchestrationEngine Protocol and its data shapes.

The Protocol carries the engine surface and no behavior; LocalEngine and
PrefectEngine satisfy it structurally, and mypy checks the conformance.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Mapping

    # Type-only import, so no runtime networkx import fires from this module.
    import networkx as nx

# mypy resolves nx.DiGraph as Any while networkx is absent; the full
# structural check restores once networkx joins the venv.


class StepStatus(StrEnum):
    """The lifecycle of one step; the string values are the on-disk lineage values."""

    SUBMITTED = "submitted"  # queued, not started; also the never-run end state
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


# The shapes below are kw_only so future engines can add or rename fields
# without a positional break at call sites. module_status is a Mapping keyed by
# step id, in execution order.


@dataclass(frozen=True, kw_only=True)
class ExecutionResult:
    """The result of one Flow execution (state-manager shape)."""

    flow_id: str
    status: str
    lab_name: str
    module_status: Mapping[str, str]
    started_at: str
    finished_at: str
    error: str | None = None
    # Transient, not persisted to the lineage record. The absent third-party
    # package when the run failed on a missing dependency, so the CLI resolves
    # dae.lab.run.missing_deps with a requirements.txt pointer; else None.
    missing_package: str | None = None
    # Transient as well. True when the emitter yielded an empty partition (M=0),
    # a successful zero-flight run with no flights/ dir; the CLI resolves it to
    # dae.lab.run.ok_empty.
    empty_partition: bool = False


@dataclass(frozen=True, kw_only=True)
class FlowStatus:
    """A read-back of a Flow's recorded lineage (status report)."""

    flow_id: str
    status: str
    lab_name: str
    module_status: Mapping[str, str]
    created_at: str


@dataclass(frozen=True, kw_only=True)
class LabConfig:
    """The per-run engine configuration."""

    lab_name: str
    lab_dir: Path
    seed: int = 0
    output_root: Path = Path("dae-outputs")
    max_workers: int = 1  # K; above 1 runs bounded waves of fresh subprocesses
    engine: str = "local"  # local, or prefect behind the [engine] extra
    isolation: str | None = None  # ambient, uv or nix; None is ambient at K=1, uv above


class OrchestrationEngine(Protocol):
    """The engine surface; behavior lives in the adapters."""

    def execute_dag(self, dag: nx.DiGraph, config: LabConfig) -> ExecutionResult:
        """Run a full module DAG under ``config`` and report the flow result."""
        ...

    def get_status(self, flow_id: str) -> FlowStatus:
        """Report the current status of the flow named ``flow_id``."""
        ...
