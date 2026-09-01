"""daedalus root command (Typer).

Builds the root Typer app, mounts the four command groups, and emits the
onboarding text when invoked bare. Both console scripts (``dae`` and
``daedalus``) point at :func:`main`.
"""

from typing import Annotated

import typer

from daedalus import __version__
from daedalus.cli import render, strings
from daedalus.cli.commands._outcome import is_json, resolve, state
from daedalus.cli.commands.example import example
from daedalus.cli.commands.flow import flow
from daedalus.cli.commands.lab import lab
from daedalus.cli.commands.module import module
from daedalus.core.outcomes import Outcome

# --help track panels. The groups bucket by function so `dae --help`
# reads as a guided surface rather than a flat list.
_TRACK_AUTHOR = "Author a Lab"
_TRACK_EXPLORE = "Start from an example"
_TRACK_INSPECT = "Inspect a run"

app = typer.Typer(
    help=strings.ROOT_TAGLINE,
    no_args_is_help=False,
    add_completion=True,
    # -h is the conventional help alias; set once on the root, Click's context
    # tree carries it down to every group and leaf without per-command wiring.
    context_settings={"help_option_names": ["-h", "--help"]},
)


def _version_callback(value: bool) -> None:
    """Print ``dae <version>`` and exit; an eager flag outside the outcome codes."""
    if value:
        typer.echo(f"dae {__version__}")
        raise typer.Exit()


app.add_typer(example, name="example", rich_help_panel=_TRACK_EXPLORE)
app.add_typer(module, name="module", rich_help_panel=_TRACK_AUTHOR)
app.add_typer(lab, name="lab", rich_help_panel=_TRACK_AUTHOR)
app.add_typer(flow, name="flow", rich_help_panel=_TRACK_INSPECT)


@app.callback(invoke_without_command=True)
def root(
    ctx: typer.Context,
    json_out: Annotated[
        bool, typer.Option("--json", help=strings.JSON_OPTION_HELP)
    ] = False,
    _version: Annotated[
        bool,
        typer.Option(
            "--version",
            "-V",
            callback=_version_callback,
            is_eager=True,
            help=strings.VERSION_OPTION_HELP,
        ),
    ] = False,
) -> None:
    """Emit the onboarding text when invoked with no subcommand.

    ``--json`` here sets the per-invocation baseline before any subcommand; a
    leaf's shared ``--json`` can then only raise it, so the flag works in
    either position.
    """
    state["json"] = json_out
    if ctx.invoked_subcommand is None:
        # Bare 'dae' (dae.onboarding.ok); the command list comes from the
        # registered groups.
        if not is_json():
            # Every add_typer above passes name=..., so no group name is None;
            # the filter only narrows the type for mypy.
            groups = [group.name for group in app.registered_groups if group.name]
            render.onboarding(groups)
        resolve(Outcome.DAE_ONBOARDING_OK)


def main() -> None:
    app()
