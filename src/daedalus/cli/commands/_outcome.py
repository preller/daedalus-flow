"""Every command names its Outcome through ``resolve``.

``resolve`` owns the exit code (0 for ok and dry_run outcomes, 2 for usage
errors). Under ``--json`` it prints the ``{code, exit, error, data}`` envelope
to plain stdout rather than the Rich console, so the machine surface stays free
of ANSI. The root ``--json`` flag sets ``state["json"]``; command bodies guard
their human output behind ``if not is_json():``.
"""

import json
from typing import Annotated, Any

import typer

from daedalus.cli import strings
from daedalus.core.outcomes import Outcome

# Process-global flag. The root callback sets the baseline before any command
# body runs; the per-leaf option below can only raise it to True, so --json
# works before or after the noun.
state = {"json": False}


def is_json() -> bool:
    """Whether the current invocation requested machine-readable JSON output."""
    return state["json"]


def _escalate_json(value: bool) -> bool:
    """Set the json flag when --json is passed; a leaf's False never lowers it."""
    if value:
        state["json"] = True
    return value


# One shared --json option reused on every leaf, so the flag is accepted after
# the noun (`dae lab visualize --json`) as well as before it.
JsonOption = Annotated[
    bool,
    typer.Option("--json", callback=_escalate_json, help=strings.JSON_OPTION_HELP),
]


def resolve(
    outcome: Outcome,
    payload: dict[str, Any] | None = None,
    *,
    error: dict[str, Any] | None = None,
) -> None:
    """Make the outcome explicit; exit non-zero only for error outcomes.

    Under ``--json``, print the ``{code, exit, error, data}`` envelope first,
    with the dotted code, its registry exit, the failure cause (null on success)
    and the command payload (null when there is none). The four-key shape is fixed.
    """
    if is_json():
        body = {
            "code": str(outcome),
            "exit": outcome.exit_code,
            "error": error,
            "data": payload or None,
        }
        print(json.dumps(body))
    if outcome.exit_code != 0:
        raise typer.Exit(code=outcome.exit_code)
