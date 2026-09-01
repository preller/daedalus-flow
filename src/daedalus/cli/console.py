"""The two Rich Consoles dae renders through.

``out`` goes to stdout, the transcript; ``err`` goes to stderr, the teaching
chrome and the Next hint. Both share one theme (``DAE_THEME``) with
highlighting and emoji off. Width is resolved once per process: ``DAE_WIDTH``
when set, the live terminal width on a tty, and ``DAE_DEFAULT_WIDTH`` when
piped or captured, so a CliRunner capture is reproducible.
"""

import os
import sys

from rich.console import Console
from rich.theme import Theme

from daedalus.core.topology import Role

DAE_DEFAULT_WIDTH = 88

# Semantic style keys for the render layer and stderr chrome, the base seven
# plus one per role. `code` has no render-layer consumer; it arrives only
# through the --json `code` field.
_THEME_STYLES = {
    "ok": "green",
    "warn": "yellow",
    "err": "bold red",
    "would": "cyan",
    "role": "magenta",
    "header": "bold",
    "muted": "dim",
    "role.emitter": "green",
    "role.transform": "cyan",
    "role.walk": "magenta",
    "role.flight": "blue",
}

DAE_THEME = Theme(_THEME_STYLES)

# One-letter glyph (the role initial) and theme style key per role. The render
# layer draws the topology table and role tags from these, so E/T/W/F is
# defined in one place.
ROLE_GLYPH: dict[Role, str] = {
    Role.EMITTER: "E",
    Role.TRANSFORM: "T",
    Role.WALK_COLLECTOR: "W",
    Role.FLIGHT_COLLECTOR: "F",
}

ROLE_STYLE: dict[Role, str] = {
    Role.EMITTER: "role.emitter",
    Role.TRANSFORM: "role.transform",
    Role.WALK_COLLECTOR: "role.walk",
    Role.FLIGHT_COLLECTOR: "role.flight",
}


def _resolve_width() -> int | None:
    """Resolve the render width once, deterministically (see module docstring)."""
    env = os.environ.get("DAE_WIDTH")
    if env:
        return int(env)
    if sys.stdout.isatty():
        return None
    return DAE_DEFAULT_WIDTH


_WIDTH = _resolve_width()

out = Console(
    file=sys.stdout,
    theme=DAE_THEME,
    highlight=False,
    emoji=False,
    soft_wrap=False,
    width=_WIDTH,
)

err = Console(
    file=sys.stderr,
    theme=DAE_THEME,
    highlight=False,
    emoji=False,
    soft_wrap=True,
    width=_WIDTH,
)
