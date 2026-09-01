"""Configuration-walk rendering and the token-set walk-string renderer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from daedalus.core.walks._shared import (
    _FLIGHT_ID,
    _GLOBAL_ROOT,
    DEFAULT_WALK_BUDGET,
    Instance,
    WalkDefect,
    WalkPlan,
    WalkRecord,
    _walk_num,
    _walk_of,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from daedalus.core.walks._propagation import _Pass


def user_walk(record: WalkRecord, walks: tuple[WalkRecord, ...]) -> str | None:
    """The presentation-only ``walk_J`` label for ``record``, or None.

    Branch walks (a set ``branch_module``) rank densely from 1 within their
    flight, in counter order. The global root and flight-root walks are the flow
    and flight scope, not user pipelines, and map to ``None``.
    """
    if record.branch_module is None:
        return None
    branches = [
        w
        for w in sorted(walks, key=lambda r: _walk_num(r.walk_id))
        if w.branch_module is not None and w.flight_id == record.flight_id
    ]
    rank = [w.walk_id for w in branches].index(record.walk_id) + 1
    return f"walk_{rank}"


def _config_full_line(p: _Pass, instances: tuple[Instance, ...]) -> str:
    """The configuration ``Full:`` shape, flight root inlined after the emitter."""
    ctx = _render_ctx(p, instances)
    return _config_segment(ctx, _GLOBAL_ROOT, p.roles)


def _config_emitter_part(ctx: _RenderCtx, roles: Mapping[str, str]) -> str:
    """The inlined flight-root walk segment that follows the emitter."""
    if ctx.flight_root is None:
        return ""
    return _config_segment(ctx, ctx.flight_root, roles)


def _config_segment(ctx: _RenderCtx, walk_id: str, roles: Mapping[str, str]) -> str:
    """One walk's instances in plan-index order, config groups inlined."""
    parts: list[str] = []
    consumed: set[str] = set()
    for instance in ctx.by_walk.get(walk_id, []):
        if instance.instance_id in consumed:
            continue
        is_fc = roles.get(instance.module_id) == "flight_collector"
        parts.append(f"[{instance.index}]" if is_fc else str(instance.index))
        if instance.module_id == ctx.emitter:
            tail = _config_emitter_part(ctx, roles)
            if tail:
                parts.append(tail)
            continue
        parts.extend(_config_group_parts(ctx, walk_id, instance, consumed, roles))
    return "-".join(parts)


def _common_suffix(members: list[str]) -> list[str]:
    """Shared trailing tokens; ``{20-22,21-22}`` renders as ``{20,21}-22``."""
    token_lists = [m.split("-") for m in members]
    shortest = min((len(t) for t in token_lists), default=0)
    shared: list[str] = []
    for offset in range(1, shortest):
        column = {tokens[-offset] for tokens in token_lists}
        if len(column) != 1:
            break
        shared.insert(0, column.pop())
    return shared


def _config_closer(closers: list[Instance]) -> str:
    """A lone collector renders ``(N)``; a sibling set renders ``{(a),(b)}``."""
    if len(closers) == 1:
        return f"({closers[0].index})"
    return "{" + ",".join(f"({c.index})" for c in closers) + "}"


def _config_group_parts(
    ctx: _RenderCtx,
    walk_id: str,
    instance: Instance,
    consumed: set[str],
    roles: Mapping[str, str],
) -> list[str]:
    """``{members}`` (shared suffix factored out) plus the marked closer(s)."""
    children = ctx.children_by_birth.get((walk_id, instance.module_id), [])
    if not children:
        return []
    key = (instance.module_id, walk_id)
    closers = [
        c for c in ctx.by_walk[walk_id] if ctx.collector_meta.get(c.instance_id) == key
    ]
    members = [_config_segment(ctx, child, roles) for child in children]
    suffix = _common_suffix(members)
    if suffix:
        keep = len(suffix)
        members = ["-".join(m.split("-")[:-keep]) for m in members]
    group = "{" + ",".join(members) + "}"
    tail = ["-".join(suffix)] if suffix else []
    if not closers:
        return [group, *tail]
    consumed.update(c.instance_id for c in closers)
    return [group, *tail, _config_closer(closers)]


def configurations(plan: WalkPlan) -> tuple[tuple[str, ...], ...]:
    """Every source-to-sink path in the instance G* DAG, the configuration walks.

    A configuration walk makes one choice at every fork, a brancher's out-edges
    or a sibling-collector set. The order is a depth-first traversal that visits
    successors in plan-index order, so the configs are listed by their path.
    """
    index_of = {i.instance_id: i.index for i in plan.instances}
    succ: dict[str, list[str]] = {}
    indeg: dict[str, int] = {i.instance_id: 0 for i in plan.instances}
    for source, target in plan.edges:
        succ.setdefault(source, []).append(target)
        indeg[target] = indeg.get(target, 0) + 1
    for children in succ.values():
        children.sort(key=lambda iid: (index_of[iid], iid))
    sources = sorted(
        (iid for iid, d in indeg.items() if d == 0),
        key=lambda iid: (index_of[iid], iid),
    )
    paths: list[tuple[str, ...]] = []

    def _walk(node: str, acc: tuple[str, ...]) -> None:
        acc = (*acc, node)
        children = succ.get(node, ())
        if not children:
            paths.append(acc)
            return
        for child in children:
            _walk(child, acc)

    for src in sources:
        _walk(src, ())
    return tuple(paths)


def _config_count(plan: WalkPlan) -> int:
    """``len(configurations(plan))`` via a memoized path count, without enumerating."""
    succ: dict[str, list[str]] = {}
    indeg: dict[str, int] = {i.instance_id: 0 for i in plan.instances}
    for source, target in plan.edges:
        succ.setdefault(source, []).append(target)
        indeg[target] = indeg.get(target, 0) + 1
    paths: dict[str, int] = {}

    def _count(node: str) -> int:
        if node in paths:
            return paths[node]
        children = succ.get(node)
        total = 1 if not children else sum(_count(child) for child in children)
        paths[node] = total
        return total

    return sum(_count(iid) for iid, deg in indeg.items() if deg == 0)


def _config_budget_defect(plan: WalkPlan, config_budget: int) -> WalkDefect | None:
    """The configuration-axis budget guard; the count is not enumerated."""
    count = _config_count(plan)
    if count <= config_budget:
        return None
    return WalkDefect(
        "config_walk_budget_exceeded",
        f"the lab expands to {count} configuration walks, over the "
        f"configuration-walk budget of {config_budget} (the cartesian product of "
        f"decision points, distinct from the {DEFAULT_WALK_BUDGET} per-flight "
        "instance budget); a fan-out this wide must be opted into knowingly, "
        "and is refused rather than truncated.",
    )


def _config_lines(plan: WalkPlan) -> tuple[str, ...]:
    """Render the configuration-walk block, ``Walks: N`` then one line per config."""
    index_of = {i.instance_id: i.index for i in plan.instances}
    module_of = {i.instance_id: i.module_id for i in plan.instances}

    def _token(instance_id: str) -> str:
        idx = index_of[instance_id]
        role = plan.roles.get(module_of[instance_id], "transform")
        if role == "walk_collector":
            return f"({idx})"
        if role == "flight_collector":
            return f"[{idx}]"
        return str(idx)

    configs = configurations(plan)
    body = [
        f"  walk_{number}: " + "-".join(_token(iid) for iid in path)
        for number, path in enumerate(configs, start=1)
    ]
    return (f"Walks: {len(configs)}", *body)


@dataclass(frozen=True)
class _RenderCtx:
    """Read-only inputs for the pure walk-string renderer."""

    by_walk: dict[str, list[Instance]]
    children_by_birth: dict[tuple[str, str], list[str]]
    collector_meta: dict[str, tuple[str | None, str]]
    records: dict[str, WalkRecord]
    parent: dict[str, str | None]
    emitter: str | None
    flight_root: str | None


def _render_ctx(p: _Pass, instances: tuple[Instance, ...]) -> _RenderCtx:
    """Index the plan for rendering, instances per walk and children per brancher."""
    by_walk: dict[str, list[Instance]] = {}
    for instance in instances:
        by_walk.setdefault(instance.walk_id, []).append(instance)
    children: dict[tuple[str, str], list[str]] = {}
    for record in p.records.values():
        if record.branch_module is None:
            continue
        if record.parent_walk is None or record.born_at is None:
            continue
        key = (record.parent_walk, record.born_at)
        children.setdefault(key, []).append(record.walk_id)
    return _RenderCtx(
        by_walk=by_walk,
        children_by_birth=children,
        collector_meta=p.collector_meta,
        records=p.records,
        parent=p.parent,
        emitter=p.emitter,
        flight_root=p.flight_root,
    )


def _walk_lineage(ctx: _RenderCtx, walk_id: str) -> set[str]:
    """Ancestors plus transitive descendants of ``walk_id``, siblings excluded."""
    line = {walk_id}
    current = ctx.parent.get(walk_id)
    while current is not None:
        line.add(current)
        current = ctx.parent.get(current)
    descendants = {walk_id}
    changed = True
    while changed:
        changed = False
        for child, parent in ctx.parent.items():
            if parent in descendants and child not in descendants:
                descendants.add(child)
                changed = True
    return line | descendants


def _run_to_sink(ctx: _RenderCtx, walk_id: str) -> str:
    """One walk's full path source-to-sink, with ``(N)`` at the merge collector."""
    lineage = _walk_lineage(ctx, walk_id)
    excluded = {
        rec.walk_id
        for rec in ctx.records.values()
        if rec.branch_module is not None and rec.walk_id not in lineage
    }
    record = ctx.records[walk_id]
    group = (record.born_at, record.parent_walk)
    markers = {
        inst.index
        for inst in _all_instances(ctx)
        if ctx.collector_meta.get(inst.instance_id) == group
    }
    by_index: dict[int, str] = {}
    for inst in _all_instances(ctx):
        if inst.walk_id in excluded:
            continue
        by_index[inst.index] = (
            f"({inst.index})" if inst.index in markers else str(inst.index)
        )
    return "-".join(by_index[i] for i in sorted(by_index))


def _all_instances(ctx: _RenderCtx) -> list[Instance]:
    """Every instance in the plan, flattened from the per-walk index."""
    return [inst for group in ctx.by_walk.values() for inst in group]


def _render_lines(
    p: _Pass, instances: tuple[Instance, ...], terminal: tuple[str, ...]
) -> tuple[str, ...]:
    """The walk block, a flight-free ``Full:`` line plus the numbered ``Walks:``."""
    ctx = _render_ctx(p, instances)
    full = _segment(ctx, _GLOBAL_ROOT, flatten=True)

    branch_walks = [
        ctx.records[w]
        for w in sorted(ctx.records, key=_walk_num)
        if ctx.records[w].branch_module is not None
    ]
    if branch_walks:
        body = [
            f"  {user_walk(rec, tuple(branch_walks))}: {_run_to_sink(ctx, rec.walk_id)}"
            for rec in branch_walks
        ]
    else:
        terminal_walk = sorted({_walk_of(i) for i in terminal}, key=_walk_num)[-1]
        body = [f"  walk_1: {_run_to_sink(ctx, terminal_walk)}"]

    return (f"Full:  {full}", f"Walks: {len(body)}", *body)


def _segment(ctx: _RenderCtx, walk_id: str, *, flatten: bool = False) -> str:
    """Render one walk's instances in plan-index order, groups inlined."""
    parts: list[str] = []
    consumed: set[str] = set()
    for instance in ctx.by_walk.get(walk_id, []):
        if instance.instance_id in consumed:
            continue
        parts.append(str(instance.index))
        if instance.module_id == ctx.emitter:
            if flatten and ctx.flight_root is not None:
                inlined = _segment(ctx, ctx.flight_root, flatten=True)
                if inlined:
                    parts.append(inlined)
            else:
                parts.append(f"<{_FLIGHT_ID}>")
            continue
        parts.extend(_group_parts(ctx, walk_id, instance, consumed))
    return "-".join(parts)


def _group_parts(
    ctx: _RenderCtx, walk_id: str, instance: Instance, consumed: set[str]
) -> list[str]:
    """'(members)' plus the closer(s) for a brancher instance's group."""
    children = ctx.children_by_birth.get((walk_id, instance.module_id), [])
    if not children:
        return []
    key = (instance.module_id, walk_id)
    closers = [
        c for c in ctx.by_walk[walk_id] if ctx.collector_meta.get(c.instance_id) == key
    ]
    members = ",".join(_segment(ctx, child) for child in children)
    if not closers:
        return [f"({members})"]
    consumed.update(c.instance_id for c in closers)
    if len(closers) == 1:
        closer = str(closers[0].index)
    else:
        closer = "[" + ",".join(str(c.index) for c in closers) + "]"
    return [f"({members})", closer]
