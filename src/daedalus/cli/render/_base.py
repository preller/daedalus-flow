"""The shared Rich primitives every render function composes.

The literal-text highlight patterns, the role-glyph cells and the borderless
grid and section helpers that print to the shared ``out`` console.
``_workflow`` and ``_topology`` import these; this module imports no sibling.
User-supplied content is rendered only through ``rich.text.Text``, which does
not parse console markup, and colored with ``highlight_regex`` over the literal
text.
"""

from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from daedalus.cli.console import ROLE_GLYPH, ROLE_STYLE, out
from daedalus.core import topology

# Highlight patterns applied to literal Text, never to markup. The role set is
# the closed 4-value vocabulary; `done` is the flow-status tag.
_ROLE_RE = r"\[(?:emitter|transform|walk_collector|flight_collector|done)\]"
_WOULD_RE = r"\bwould\b"
# The two preview lines (NOTHING_EXECUTED and PREVIEW_ONLY), rendered muted.
_PREVIEW_LINE_RE = (
    r"nothing was executed \(preview only\)|\(preview only - nothing was written\)"
)


def _prose(text: str) -> Text:
    """A literal Text (markup never parsed) with safe semantic highlights."""
    t = Text(text)
    t.highlight_regex(_ROLE_RE, "role")
    t.highlight_regex(_WOULD_RE, "would")
    t.highlight_regex(_PREVIEW_LINE_RE, "muted")
    return t


def _glyph_cell(role: topology.Role) -> Text:
    """The single-letter role glyph (E/T/W/F), themed per role."""
    return Text(ROLE_GLYPH[role], style=ROLE_STYLE[role])


def _role_legend() -> Text:
    """One legend line mapping each glyph to its role word."""
    legend = Text("legend:  ", style="muted")
    pairs = [
        (topology.Role.EMITTER, "emitter"),
        (topology.Role.TRANSFORM, "transform"),
        (topology.Role.WALK_COLLECTOR, "walk-collector"),
        (topology.Role.FLIGHT_COLLECTOR, "flight-collector"),
    ]
    for i, (role, word) in enumerate(pairs):
        if i:
            legend.append("   ", style="muted")
        legend.append(ROLE_GLYPH[role], style=ROLE_STYLE[role])
        legend.append(f" {word}", style="muted")
    return legend


def preview_banner(title: str) -> None:
    """Frame a --dry-run preview affordance in a Panel (called by the command)."""
    out.print(Panel(Text(title, style="would"), expand=False, border_style="would"))


# Thin wrappers over Rich grids, so every report shares one shape.


def report_header(text: str) -> Group:
    """A styled header line followed by a Rule: the standard section opener."""
    return Group(Text(text, style="header"), Rule(style="muted"))


def kv_grid(rows: list[tuple[str, str]]) -> Table:
    """A borderless key/value grid (key muted, value default)."""
    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="muted")
    grid.add_column()
    for key, value in rows:
        grid.add_row(key, Text(value))
    return grid


def command_grid(pairs: list[tuple[str, str]]) -> Table:
    """A two-column command/gloss grid (command in the ok style, gloss muted)."""
    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="ok")
    grid.add_column(style="muted")
    for command, gloss in pairs:
        grid.add_row(Text(command), Text(gloss))
    return grid


def section(*renderables: RenderableType) -> None:
    """Print each renderable once to the contract stream (stdout)."""
    for renderable in renderables:
        out.print(renderable)
