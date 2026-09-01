"""List the example ladder or scaffold one example (the ``example`` command).

A thin command layer over the pure functions in ``strings``; teaching notes and
the Next hint go to stderr through ``chrome``. ``example`` takes an optional
positional name, so it is a one-callback Typer mounted with ``add_typer``, which
makes both ``dae example`` and ``dae example minimal`` work. The bare ladder is
example.list.ok, a known example example.scaffold.ok and an unknown one
example.scaffold.not_found (exit 2).
"""

from typing import Annotated

import typer

from daedalus.cli import chrome, render, strings
from daedalus.cli.commands._outcome import JsonOption, is_json, resolve
from daedalus.cli.console import out
from daedalus.core import paths
from daedalus.core.outcomes import Outcome

example = typer.Typer(
    help="Show the example ladder, or scaffold a single example by name.",
    invoke_without_command=True,
    no_args_is_help=False,
)

# The example names with a bundle directory on disk, from strings so the
# ladder and the command agree; any other name is refused as unknown.
_BUNDLED_EXAMPLES = set(strings.AVAILABLE_EXAMPLES)


def _scaffold_bundled(name: str) -> None:
    """Copy the bundled example ``name`` into ``./<name>/``, refusing to clobber."""
    dest = paths.example_dir(name)
    if dest.exists():
        if not is_json():
            chrome.note(f"'{name}' already exists here; refusing to overwrite it.")
        return resolve(Outcome.DAE_EXAMPLE_SCAFFOLD_EXISTS)
    paths.copy_example_bundle(name, dest)
    if not is_json():
        # The result path goes to stdout so an agent capturing stdout alone
        # learns where the example landed; the teaching note + Next hint stay on
        # stderr. The path is the one machine-relevant fact of a scaffold.
        out.print(f"scaffolded ./{name}/")
        chrome.note(f"scaffolded example '{name}' into ./{name}/")
        # Point at the input/ dir when the scaffolded bundle ships one (detected
        # on disk).
        input_dir = dest / "input"
        if input_dir.is_dir():
            inputs = sorted(p for p in input_dir.iterdir() if p.is_file())
            if inputs:
                rel = f"{name}/input/{inputs[0].name}"
                chrome.note(strings.INPUT_DIR_HINT.format(input_file=rel))
        chrome.next_line(strings.NEXT_AFTER_SCAFFOLD[name])
    return resolve(Outcome.EXAMPLE_SCAFFOLD_OK, payload={"paths": [str(dest)]})


def _example_entries() -> list[dict[str, object]]:
    """The example ladder as ``--json`` entries, simplest first."""
    return [
        {
            "name": name,
            "available": name in _BUNDLED_EXAMPLES,
            "description": description,
        }
        for name, description in strings.example_rows()
    ]


@example.callback(invoke_without_command=True)
def example_main(
    name: Annotated[
        str | None,
        typer.Argument(help="Example to scaffold; omit to list the ladder."),
    ] = None,
    json_out: JsonOption = False,
) -> None:
    """Show the example ladder, or scaffold a single example by name."""
    if name is None:
        # Bare 'dae example': list the ladder, point at the simplest example.
        if not is_json():
            render.example_ladder()
            chrome.next_line("dae example minimal")
        # Under --json, attach the ladder as an array built from the same
        # strings data as the human render, so the two surfaces agree.
        return resolve(
            Outcome.EXAMPLE_LIST_OK, payload={"examples": _example_entries()}
        )

    if name in _BUNDLED_EXAMPLES:
        return _scaffold_bundled(name)

    # An unknown example gets a stderr note and the usage exit code.
    if not is_json():
        chrome.note(f"unknown example '{name}'.")
        chrome.note("valid examples: " + ", ".join(strings.KNOWN_EXAMPLES))
    return resolve(Outcome.EXAMPLE_SCAFFOLD_NOT_FOUND)
