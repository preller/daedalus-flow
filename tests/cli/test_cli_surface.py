"""The CLI command tree matches a committed golden; any surface change goes red.

Regenerate the golden with ``UPDATE_CLI_SURFACE=1`` and review the diff.
"""

from __future__ import annotations

import os
from pathlib import Path

import typer

from daedalus.cli.app import app

_GOLDEN = Path(__file__).parent / "cli_surface.golden.txt"


def _param_sig(param: object) -> str | None:
    """A stable, ANSI-free signature for one Click parameter, or None to skip it."""
    # --help, --install-completion and --show-completion are framework noise on
    # the root and would bury real changes.
    name = getattr(param, "name", None)
    if name in {"help", "install_completion", "show_completion"}:
        return None
    type_name = getattr(getattr(param, "type", None), "name", "?")
    if getattr(param, "param_type_name", "") == "argument":
        suffix = "" if getattr(param, "required", False) else "?"
        return f"<{name}:{type_name}{suffix}>"
    opts = sorted(getattr(param, "opts", []) or [name])
    primary = opts[0]
    body = (
        f"{primary}:flag"
        if getattr(param, "is_flag", False)
        else f"{primary}:{type_name}"
    )
    return body + ("*" if getattr(param, "required", False) else "")


def _walk(command: object, path: str) -> list[str]:
    """Render ``command`` and its descendants as sorted ``path :: params`` lines."""
    sigs: list[str] = []
    for param in getattr(command, "params", []):
        sig = _param_sig(param)
        if sig is not None:
            sigs.append(sig)
    sigs.sort()
    lines = [f"{path} :: {' '.join(sigs)}".rstrip()]
    subcommands = getattr(command, "commands", {}) or {}
    for name in sorted(subcommands):
        lines.extend(_walk(subcommands[name], f"{path} {name}"))
    return lines


def _render_surface() -> str:
    """The whole CLI surface as a deterministic multi-line string."""
    cli = typer.main.get_command(app)
    return "\n".join(_walk(cli, "dae")) + "\n"


def test_cli_surface_matches_golden() -> None:
    """UPDATE_CLI_SURFACE=1 rewrites the golden before the comparison."""
    surface = _render_surface()
    if os.environ.get("UPDATE_CLI_SURFACE"):
        _GOLDEN.write_text(surface)
    assert _GOLDEN.exists(), (
        "cli_surface.golden.txt missing; regenerate with "
        "UPDATE_CLI_SURFACE=1 python -m pytest tests/cli/test_cli_surface.py"
    )
    assert surface == _GOLDEN.read_text(), (
        "CLI surface changed. If intended, regenerate the golden with "
        "UPDATE_CLI_SURFACE=1 and review the diff; a new/renamed command also "
        "needs an outcome code (test_outcome_contract.py) and a test row."
    )
