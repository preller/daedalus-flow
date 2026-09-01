"""Lineage schema, the on-disk dataclasses and the format-version constants.

The pure-data half of the lineage record: the reserved file names, the
format-version constants, :class:`LineageError`, and the four frozen
dataclasses (:class:`WalkRecord`, :class:`StepManifest`, :class:`FlowStep`,
:class:`FlowRecord`) with their ``to_json`` and ``from_json``. The I/O half
lives in ``_io`` and imports from here; this module does not import back.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from daedalus import __version__ as _DAEDALUS_VERSION

if TYPE_CHECKING:
    from typing import SupportsFloat, SupportsInt

# Highest version this build reads. Writers pick the lowest version that
# fits the record, so old goldens do not move:
#   1 no walk fields | 2 walk fields | 3 user_walk | 4 per-step timing
FORMAT_VERSION = 4

# The version a record whose steps carry per-step wall-clock timing is written as.
_TIMING_FORMAT_VERSION = 4

# The version a walk-model record with the v3 ``walk_J`` numbering but no step
# timing is written as. Pinned apart from ``FORMAT_VERSION`` so a later bump
# does not move the v3 goldens.
_USER_WALK_FORMAT_VERSION = 3

# The version a walk-model record without the v3 user-facing numbering is written
# as, so the walk-model goldens stay byte stable until the engine cutover
# populates ``user_walk``. Bumping ``FORMAT_VERSION`` must not move these.
_WALK_MODEL_FORMAT_VERSION = 2

# The version a record without any of the additive walk-model fields is written
# as, so engine output unchanged by the walk-model cutover keeps its old bytes.
_LEGACY_FORMAT_VERSION = 1

# Reserved file names (the ``dae-`` prefix namespace; modules must not write
# ``dae-*`` files, so these never collide with module outputs).
STEP_MANIFEST_NAME = "dae-manifest.json"
FLOW_RECORD_NAME = "dae-flow.json"
# The reserved prefix for all daedalus-owned files (the manifests above). Modules
# must not write ``dae-*`` files, so excluding this prefix cleanly isolates a
# module's own outputs when copying them into the per-flow ``output/`` dir.
RESERVED_PREFIX = "dae-"


class LineageError(Exception):
    """A lineage file is unreadable or carries an unknown ``format_version``."""


@dataclass(frozen=True)
class WalkRecord:
    """One walk's record in ``dae-flow.json``, kept stdlib-only apart from walks."""

    walk_id: str  # internal ``w<id>`` propagation token; lineage and seed key only
    flight_id: str | None  # runtime flight (``flight_1..N``); None for the global root
    parent_walk: str | None
    born_at: str | None  # the minting brancher edge, with branch_module
    branch_module: str | None
    user_walk: str | None = None  # v3 ``walk_J`` label per flight; None on root walks

    def to_json(self) -> dict[str, object]:
        """Serialize the walk record, emitting ``user_walk`` only when set.

        Omitting ``user_walk`` when it is ``None`` keeps a pre-v3 walk record byte
        identical to its version-2 form (the additive-key discipline).
        """
        payload: dict[str, object] = {
            "walk_id": self.walk_id,
            "flight_id": self.flight_id,
            "parent_walk": self.parent_walk,
            "born_at": self.born_at,
            "branch_module": self.branch_module,
        }
        if self.user_walk is not None:
            payload["user_walk"] = self.user_walk
        return payload

    @classmethod
    def from_json(cls, data: dict[str, object]) -> WalkRecord:
        return cls(
            walk_id=str(data["walk_id"]),
            flight_id=_opt_str(data.get("flight_id")),
            parent_walk=_opt_str(data.get("parent_walk")),
            born_at=_opt_str(data.get("born_at")),
            branch_module=_opt_str(data.get("branch_module")),
            user_walk=_opt_str(data.get("user_walk")),
        )


@dataclass(frozen=True)
class StepManifest:
    """The per-step lineage record (``dae-manifest.json``)."""

    step_id: str
    status: str
    seed: int
    started_at: str | None = None
    finished_at: str | None = None
    duration_s: float | None = None
    error: str | None = None
    error_code: str | None = None  # the dae.step.* code; emitted only when set
    flight_id: str | None = None  # walk-model field (version 2); absent on a v1 record
    walk_id: str | None = None  # walk-model field (version 2)
    instance_id: str | None = None  # walk-model field (version 2)

    def _has_walk_fields(self) -> bool:
        """True iff any additive walk-model field is populated (=> version 2)."""
        return (
            self.flight_id is not None
            or self.walk_id is not None
            or self.instance_id is not None
        )

    def to_json(self) -> dict[str, object]:
        """Serialize to the manifest dict, ``format_version`` first.

        A record with no walk-model fields stays version 1 with those keys
        absent; one with them is version 2 and adds them after ``error``.
        """
        payload: dict[str, object] = {
            "format_version": (
                _WALK_MODEL_FORMAT_VERSION
                if self._has_walk_fields()
                else _LEGACY_FORMAT_VERSION
            ),
            "step_id": self.step_id,
            "status": self.status,
            "seed": self.seed,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_s": self.duration_s,
            "error": self.error,
        }
        # error_code (the dae.step.* identity) rides next to error, emitted only
        # when present so a successful or pre-taxonomy manifest keeps its prior
        # bytes (additive-when-present, like the walk-model fields below).
        if self.error_code is not None:
            payload["error_code"] = self.error_code
        if self._has_walk_fields():
            payload["flight_id"] = self.flight_id
            payload["walk_id"] = self.walk_id
            payload["instance_id"] = self.instance_id
        return payload

    @classmethod
    def from_json(cls, data: dict[str, object]) -> StepManifest:
        """Build from a parsed manifest dict (version already checked)."""
        return cls(
            step_id=str(data["step_id"]),
            status=str(data["status"]),
            seed=_as_int(data["seed"]),
            started_at=_opt_str(data.get("started_at")),
            finished_at=_opt_str(data.get("finished_at")),
            duration_s=_opt_float(data.get("duration_s")),
            error=_opt_str(data.get("error")),
            error_code=_opt_str(data.get("error_code")),
            flight_id=_opt_str(data.get("flight_id")),
            walk_id=_opt_str(data.get("walk_id")),
            instance_id=_opt_str(data.get("instance_id")),
        )


@dataclass(frozen=True)
class FlowStep:
    """One entry in the per-flow ``steps`` list."""

    step_id: str
    status: str
    duration_s: float | None = None
    started_at: str | None = None  # v4 wall-clock interval; serialized only when set
    finished_at: str | None = None
    error: str | None = None  # failure message mirrored from the StepManifest
    error_code: str | None = None  # the dae.step.* code naming how the step failed

    def _has_timing(self) -> bool:
        """True iff this step carries a wall-clock interval (lineage v4)."""
        return self.started_at is not None or self.finished_at is not None

    def to_json(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "step_id": self.step_id,
            "status": self.status,
            "duration_s": self.duration_s,
        }
        if self._has_timing():
            payload["started_at"] = self.started_at
            payload["finished_at"] = self.finished_at
        if self.error is not None:
            payload["error"] = self.error
        # error_code (the dae.step.* identity) follows error, present only when set
        # so a successful step keeps its prior bytes.
        if self.error_code is not None:
            payload["error_code"] = self.error_code
        return payload

    @classmethod
    def from_json(cls, data: dict[str, object]) -> FlowStep:
        return cls(
            step_id=str(data["step_id"]),
            status=str(data["status"]),
            duration_s=_opt_float(data.get("duration_s")),
            started_at=_opt_str(data.get("started_at")),
            finished_at=_opt_str(data.get("finished_at")),
            error=_opt_str(data.get("error")),
            error_code=_opt_str(data.get("error_code")),
        )


@dataclass(frozen=True)
class FlowRecord:
    """The per-flow lineage record (``dae-flow.json``)."""

    flow_id: str
    lab_name: str
    status: str
    created_at: str
    steps: tuple[FlowStep, ...]
    daedalus_version: str = _DAEDALUS_VERSION
    walks: tuple[WalkRecord, ...] = ()  # walk-model field; empty on a v1 record
    engine: str = "local"  # serialized only when not the default
    max_workers: int = 1  # the K knob; serialized only when not the default
    owner_pid: int | None = None  # owner stamp of a non-terminal record; cleared on end
    owner_create_time: float | None = None  # with owner_pid; live run or crash

    def to_json(self) -> dict[str, object]:
        """Serialize to the flow-record dict, ``format_version`` first.

        The lowest version that carries the record is chosen (see
        ``_format_version``), so older bytes do not move under a later bump.
        """
        payload: dict[str, object] = {
            "format_version": self._format_version(),
            "flow_id": self.flow_id,
            "lab_name": self.lab_name,
            "status": self.status,
            "created_at": self.created_at,
            "daedalus_version": self.daedalus_version,
            "steps": [step.to_json() for step in self.steps],
        }
        if self.walks:
            payload["walks"] = [walk.to_json() for walk in self.walks]
        if self.engine != "local":
            payload["engine"] = self.engine
        if self.max_workers != 1:
            payload["max_workers"] = self.max_workers
        # The owner stamp rides only the non-terminal record, so a terminal
        # (completed/failed) record stays byte-identical to the prior goldens.
        if self.owner_pid is not None:
            payload["owner_pid"] = self.owner_pid
            payload["owner_create_time"] = self.owner_create_time
        return payload

    def _format_version(self) -> int:
        """The lowest schema version that carries this record without data loss."""
        if any(
            step.started_at is not None or step.finished_at is not None
            for step in self.steps
        ):
            return _TIMING_FORMAT_VERSION
        if not self.walks:
            return _LEGACY_FORMAT_VERSION
        if any(walk.user_walk is not None for walk in self.walks):
            return _USER_WALK_FORMAT_VERSION
        return _WALK_MODEL_FORMAT_VERSION

    @classmethod
    def from_json(cls, data: dict[str, object]) -> FlowRecord:
        raw_steps = data.get("steps")
        steps = raw_steps if isinstance(raw_steps, list) else []
        raw_walks = data.get("walks")
        walks = raw_walks if isinstance(raw_walks, list) else []
        return cls(
            flow_id=str(data["flow_id"]),
            lab_name=str(data["lab_name"]),
            status=str(data["status"]),
            created_at=str(data["created_at"]),
            steps=tuple(FlowStep.from_json(s) for s in steps),
            daedalus_version=str(data.get("daedalus_version", "")),
            walks=tuple(WalkRecord.from_json(w) for w in walks),
            engine=str(data.get("engine", "local")),
            max_workers=_as_int(data["max_workers"]) if "max_workers" in data else 1,
            owner_pid=_as_int(data["owner_pid"]) if "owner_pid" in data else None,
            owner_create_time=_opt_float(data.get("owner_create_time")),
        )


def _as_int(value: object) -> int:
    """Coerce a JSON-parsed value to ``int`` (lineage ``seed`` field)."""
    return int(cast("SupportsInt", value))


def _opt_str(value: object) -> str | None:
    """Return ``value`` as ``str`` or ``None`` (lineage nullable string field)."""
    return None if value is None else str(value)


def _opt_float(value: object) -> float | None:
    """Return ``value`` as ``float`` or ``None`` (lineage nullable float field)."""
    return None if value is None else float(cast("SupportsFloat", value))
