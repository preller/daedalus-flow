"""Render the onboarding grid, the example ladder and the module and lab prose.

Composes the primitives from ``_base`` over the copy in ``strings``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from rich.text import Text

from daedalus.cli import strings
from daedalus.cli.console import out

from ._base import _prose, command_grid, kv_grid, section

if TYPE_CHECKING:
    from daedalus.core.recipe import ExecutionPlan


def lab_run_plan_payload(plan: ExecutionPlan) -> dict[str, Any]:
    """The ``--json`` mirror of :func:`render._topology.lab_run_plan`.

    One row per resolved step with ``order``, ``module``, ``role`` and
    ``module_dir``. No per-step input or output paths; the plan does not carry
    them, the engine derives them at run time and a dry run never reaches it.
    """
    return {
        "plan": [
            {
                "order": step.index,
                "module": step.module_id,
                "role": step.role,
                "module_dir": str(step.module_dir),
            }
            for step in plan.steps
        ]
    }


def onboarding(groups: list[str]) -> None:
    """Print the bare ``dae`` grid, its command list from the registered groups."""
    section(
        Text(strings.ROOT_TAGLINE, style="header"),
        Text(""),
        Text(strings.ONBOARDING_WAYS_LABEL),
        command_grid(strings.ONBOARDING_WAYS),
        Text(""),
        _prose(strings.commands_line(groups)),
        Text(strings.ONBOARDING_HELP_HINT, style="muted"),
    )


def example_ladder() -> None:
    section(
        Text(strings.EXAMPLE_LADDER_HEADER),
        Text(""),
        command_grid(strings.example_rows()),
    )


def lab_init(name: str) -> None:
    out.print(_prose(strings.lab_init(name)))


def lab_init_done(name: str) -> None:
    """The post-write summary, real-write path only, no preview banner."""
    out.print(_prose(strings.lab_init_done(name)))


def module_create(module_id: str) -> None:
    out.print(_prose(strings.module_create(module_id)))


def module_create_done(module_id: str) -> None:
    """The post-write summary, real-write path only, no preview banner."""
    out.print(_prose(strings.module_create_done(module_id)))


def module_try(path: str) -> None:
    section(
        _prose(strings.try_intro(path)),
        Text(""),
        Text(strings.TRY_CONTEXT_LABEL, style="muted"),
        kv_grid(strings.module_try_context(path)),
        Text(""),
        Text(strings.TRY_NOTE, style="muted"),
        Text(""),
        Text(strings.NOTHING_EXECUTED, style="muted"),
    )


def module_validate(path: str, unresolved_markers: int = 0) -> None:
    section(
        Text(f"module well-formed - {path}", style="ok"),
        kv_grid(strings.module_validate_rows(path, unresolved_markers)),
    )


def module_convert_map(script: str, module_id: str) -> None:
    """The convert preview prose; the command prints the --dry-run banner itself."""
    out.print(_prose(strings.module_convert(script, module_id)))


def module_convert_done(script: str, module_id: str) -> None:
    """The post-write convert summary, real-write path only, no banner."""
    out.print(_prose(strings.module_convert_done(script, module_id)))
