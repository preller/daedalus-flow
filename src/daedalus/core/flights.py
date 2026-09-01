"""Runtime flight fan-out (M>1), the post-emitter expansion step.

``walks.propagate`` is frozen at M=1 and emits one per-flight skeleton with
flight id ``f1``. After the emitter completes, this module reads M once from
its output partition. It clones the flight-scope walks, instances and
intra-flight edges M times, with fresh walk tokens and flight ids ``f1..fM``;
the emitter and flight_collector instances stay single, wired to every flight.
Flight 1 reuses the M=1 tokens, so a one-flight run matches the M=1 plan.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

from daedalus.core.walks import Instance, WalkPlan, WalkRecord, _walk_num

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

_RESERVED_SEPARATOR = "@"


def flight_index_of(flight_id: str) -> int:
    """The 1-based runtime flight number K for a flight id token ``fK``.

    The user-facing ``flight_K`` directory index is derived from the flight id
    token, never re-counted downstream.
    """
    return int(flight_id[1:])


def read_partition_count(emitter_dir: Path) -> int:
    """M = the length of the emitter's output partition, read once.

    A fan-out emitter writes a single JSON array, one entry per flight; M is its
    length and nothing downstream re-derives it. Anything else (a marker dict,
    several files, no JSON) is a static emitter, so M=1. An empty list is M=0.
    """
    candidates = sorted(
        p
        for p in emitter_dir.glob("*.json")
        if p.is_file() and not p.name.startswith("dae-")
    )
    if len(candidates) != 1:
        return 1  # not a single-roster fan-out emitter: the degenerate one flight
    partition = json.loads(candidates[0].read_text())
    if not isinstance(partition, list):
        return 1  # a static emitter (e.g. a marker dict): the degenerate one flight
    return len(partition)


def _is_flight_scope(record: WalkRecord) -> bool:
    """A flight-scope walk carries a flight id; root walks (emitter / sink) do not."""
    return record.flight_id is not None


@dataclass(frozen=True)
class _Skeleton:
    """The per-flight skeleton extracted from the M=1 plan (the clone template)."""

    plan: WalkPlan
    flight_walk_ids: frozenset[str]
    flight_iids: frozenset[str]
    flight_instances: tuple[Instance, ...]
    record_of: Mapping[str, WalkRecord]


def _skeleton(plan: WalkPlan) -> _Skeleton:
    flight_walk_ids = frozenset(r.walk_id for r in plan.walks if _is_flight_scope(r))
    flight_instances = tuple(
        inst for inst in plan.instances if inst.walk_id in flight_walk_ids
    )
    return _Skeleton(
        plan=plan,
        flight_walk_ids=flight_walk_ids,
        flight_iids=frozenset(i.instance_id for i in flight_instances),
        flight_instances=flight_instances,
        record_of={r.walk_id: r for r in plan.walks},
    )


def _token_maps(skel: _Skeleton, m: int) -> dict[int, dict[str, str]]:
    """Per-flight token maps; flight 1 keeps the originals, the rest mint fresh."""
    sorted_walks = sorted(skel.flight_walk_ids, key=_walk_num)
    maps: dict[int, dict[str, str]] = {1: {wid: wid for wid in skel.flight_walk_ids}}
    next_token = max(_walk_num(r.walk_id) for r in skel.plan.walks) + 1
    for k in range(2, m + 1):
        token_map: dict[str, str] = {}
        for wid in sorted_walks:
            token_map[wid] = f"w{next_token}"
            next_token += 1
        maps[k] = token_map
    return maps


def _relabel_iid(iid: str, token_map: Mapping[str, str]) -> str:
    """Rewrite the walk token in an instance id ``module@w<id>`` via ``token_map``."""
    module_id, _, walk_id = iid.partition(_RESERVED_SEPARATOR)
    return f"{module_id}{_RESERVED_SEPARATOR}{token_map[walk_id]}"


def _cloned_records(
    skel: _Skeleton, token_maps: Mapping[int, Mapping[str, str]], m: int
) -> tuple[WalkRecord, ...]:
    """Root records unchanged; flight records relabeled per flight (token + id)."""
    sorted_walks = sorted(skel.flight_walk_ids, key=_walk_num)
    records: list[WalkRecord] = [r for r in skel.plan.walks if not _is_flight_scope(r)]
    for k in range(1, m + 1):
        records.extend(_flight_records(skel, sorted_walks, token_maps[k], k))
    return tuple(sorted(records, key=lambda r: _walk_num(r.walk_id)))


def _flight_records(
    skel: _Skeleton, sorted_walks: list[str], token_map: Mapping[str, str], k: int
) -> list[WalkRecord]:
    out: list[WalkRecord] = []
    for wid in sorted_walks:
        src = skel.record_of[wid]
        parent = src.parent_walk
        new_parent = token_map[parent] if parent in skel.flight_walk_ids else parent
        out.append(
            WalkRecord(
                walk_id=token_map[wid],
                flight_id=f"f{k}",
                parent_walk=new_parent,
                born_at=src.born_at,
                branch_module=src.branch_module,
            )
        )
    return out


def _cloned_instances(
    skel: _Skeleton, token_maps: Mapping[int, Mapping[str, str]], m: int
) -> tuple[Instance, ...]:
    """Root instances unchanged; flight instances cloned per flight, index kept."""
    instances: list[Instance] = [
        inst for inst in skel.plan.instances if inst.instance_id not in skel.flight_iids
    ]
    for k in range(1, m + 1):
        instances.extend(_flight_instances(skel, token_maps[k]))
    return tuple(sorted(instances, key=lambda i: (i.index, _walk_num(i.walk_id))))


def _flight_instances(skel: _Skeleton, token_map: Mapping[str, str]) -> list[Instance]:
    return [
        Instance(
            instance_id=_relabel_iid(inst.instance_id, token_map),
            module_id=inst.module_id,
            walk_id=token_map[inst.walk_id],
            index=inst.index,
        )
        for inst in skel.flight_instances
    ]


def _cloned_edges(
    skel: _Skeleton,
    intra: set[tuple[str, str]],
    token_maps: Mapping[int, Mapping[str, str]],
    m: int,
) -> tuple[tuple[str, str], ...]:
    """Intra-flight edges (relabeled per flight) + boundary + root-only edges."""
    edges: set[tuple[str, str]] = set(intra)
    for s, t in skel.plan.edges:
        edges |= _boundary_edges(skel, s, t, token_maps, m)
    return tuple(sorted(edges))


def _boundary_edges(
    skel: _Skeleton,
    s: str,
    t: str,
    token_maps: Mapping[int, Mapping[str, str]],
    m: int,
) -> set[tuple[str, str]]:
    s_flight = s in skel.flight_iids
    t_flight = t in skel.flight_iids
    if s_flight and t_flight:
        return set()  # intra-flight, already covered by the relabeled intra edges
    if not s_flight and not t_flight:
        return {(s, t)}  # root -> root (emitter -> flight_collector)
    if s_flight:  # flight tail -> root sink, one edge per flight clone
        return {(_relabel_iid(s, token_maps[k]), t) for k in range(1, m + 1)}
    return {
        (s, _relabel_iid(t, token_maps[k])) for k in range(1, m + 1)
    }  # root -> flight


def _cloned_walk_inputs(
    skel: _Skeleton, token_maps: Mapping[int, Mapping[str, str]], m: int
) -> dict[str, dict[str, str]]:
    """Flight-scope walk_collector inputs cloned per flight; root inputs kept as-is."""
    out: dict[str, dict[str, str]] = {}
    for collector_iid, mapping in skel.plan.walk_inputs.items():
        if collector_iid not in skel.flight_iids:
            out[collector_iid] = dict(mapping)
            continue
        for k in range(1, m + 1):
            out[_relabel_iid(collector_iid, token_maps[k])] = _relabel_mapping(
                mapping, token_maps[k]
            )
    return out


def _relabel_mapping(
    mapping: Mapping[str, str], token_map: Mapping[str, str]
) -> dict[str, str]:
    return {
        token_map.get(walk_id, walk_id): _relabel_iid(tail, token_map)
        for walk_id, tail in mapping.items()
    }


def _cloned_terminal(
    skel: _Skeleton, token_maps: Mapping[int, Mapping[str, str]], m: int
) -> tuple[str, ...]:
    out: set[str] = set()
    for iid in skel.plan.terminal:
        if iid not in skel.flight_iids:
            out.add(iid)
            continue
        out.update(_relabel_iid(iid, token_maps[k]) for k in range(1, m + 1))
    return tuple(sorted(out))


def expand_flights(plan: WalkPlan, m: int) -> WalkPlan:
    """Clone the per-flight skeleton of ``plan`` into M flights (M >= 1).

    ``plan`` is the M=1 :class:`WalkPlan` from :func:`walks.propagate`. The
    flight-scope walks, instances and intra-flight edges are cloned M times with
    disjoint tokens and distinct flight ids; the root-scope nodes stay single.
    """
    if m < 1:
        msg = f"expand_flights requires M >= 1 (M=0 handled before expansion); got {m}"
        raise ValueError(msg)

    skel = _skeleton(plan)
    # M=1, or a flightless plan, needs no clone; the one-flight tree stays
    # byte-identical to the pre-expansion plan.
    if m == 1 or not skel.flight_walk_ids:
        return plan

    token_maps = _token_maps(skel, m)

    # Intra-flight G* edges, relabeled per flight clone (nodes = flight instances).
    intra_skeleton = [
        (s, t) for s, t in plan.edges if s in skel.flight_iids and t in skel.flight_iids
    ]
    intra_edges: set[tuple[str, str]] = {
        (_relabel_iid(s, token_maps[k]), _relabel_iid(t, token_maps[k]))
        for s, t in intra_skeleton
        for k in range(1, m + 1)
    }

    return WalkPlan(
        walks=_cloned_records(skel, token_maps, m),
        instances=_cloned_instances(skel, token_maps, m),
        edges=_cloned_edges(skel, intra_edges, token_maps, m),
        walk_inputs=_cloned_walk_inputs(skel, token_maps, m),
        terminal=_cloned_terminal(skel, token_maps, m),
        roles=dict(plan.roles),
        config_full=plan.config_full,
        _lines=plan.walk_lines(),
    )
