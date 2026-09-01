"""The 'module' command group: per-module scaffolding, smoke tests, and conversion.

Thin command layer only. Each body renders through the render layer (Rich), then
adds teaching chrome plus a Next hint on stderr. No file I/O. All four
subcommands return normally (exit 0): module.create.ok, module.try.ok,
module.validate.ok, and module.convert.dry_run / module.convert.ok. The 'try'
command keeps the Python name ``try_`` (``try`` is a keyword) but registers as
``name="try"``. The ``--dry-run`` preview banner is framed by the command body.
"""

import importlib.util
from pathlib import Path
from typing import Annotated

import typer

from daedalus.cli import chrome, render, strings
from daedalus.cli.commands._outcome import JsonOption, is_json, resolve
from daedalus.core import paths, recipe
from daedalus.core.outcomes import Outcome
from daedalus.flow import Role

module = typer.Typer(
    help="Create, try, validate or convert a single module.",
    no_args_is_help=True,
)

# The closed role vocabulary, read straight off the public Role enum so this
# check can never drift from the four canonical roles.
_CLOSED_ROLES = {str(role) for role in Role}


def _note_human(message: str) -> None:
    """Write a stderr note only on the human (non-json) surface."""
    if not is_json():
        chrome.note(message)


def _manifest_text() -> str:
    """The generated ``dae-module.yaml``, a commented ``role: transform`` line."""
    return f"{strings.MODULE_ROLE_COMMENT}\nrole: transform\n"


def _module_stub(module_id: str) -> str:
    """A ``main.py`` stub whose ``@dae.entry`` function is named ``module_id``."""
    return (
        f'"""{module_id} - a daedalus module (scaffolded by `dae module create`)."""\n'
        "\n"
        "import daedalus.flow as dae\n"
        "\n"
        "\n"
        "@dae.entry\n"
        f"def {module_id}(ctx: dae.FlowContext) -> None:\n"
        "    # Read from ctx.step_input_path, write results into"
        " ctx.step_output_path,\n"
        "    # then delete the raise to run this module.\n"
        '    raise NotImplementedError(f"{ctx.step_id}: implement this module")\n'
    )


def _module_id_from_script(script_path: Path) -> str:
    """A legal Python identifier derived from the script stem."""
    ident = "".join(c if (c.isalnum() or c == "_") else "_" for c in script_path.stem)
    if not ident or not (ident[0].isalpha() or ident[0] == "_"):
        ident = f"m_{ident}"
    return ident


def _converted_stub(module_id: str, script_path: Path, script_body: str) -> str:
    """A ``main.py`` wrapping ``script_body`` in an ``@dae.entry`` function."""
    indented = "\n".join(
        f"    {line}" if line.strip() else "" for line in script_body.splitlines()
    )
    body = indented if script_body.strip() else "    pass"
    # The ctx read/write pattern as a comment block; the lines come from
    # strings.CTX_WIRING_SNIPPET so the example and the stub stay in sync.
    # The raise above the pasted body keeps an unwired module from running.
    snippet = "\n".join(f"    #     {line}" for line in strings.CTX_WIRING_SNIPPET)
    return (
        f'"""{module_id} - converted from {script_path.name} by '
        '`dae module convert`."""\n'
        "\n"
        "import daedalus.flow as dae\n"
        "\n"
        "\n"
        "@dae.entry\n"
        f"def {module_id}(ctx: dae.FlowContext) -> None:\n"
        "    # Wire inputs from ctx.step_input_path and write outputs to"
        " ctx.step_output_path;\n"
        "    # replace the pasted script's file IO below with those paths, e.g.:\n"
        f"{snippet}\n"
        "    # then delete the raise to run this module.\n"
        '    raise NotImplementedError(f"{ctx.step_id}: implement this module")\n'
        f"{body}\n"
    )


def _role_defect(module_dir: Path) -> Outcome | None:
    """The bad_role Outcome of an unreadable or out-of-set role, else None."""
    try:
        role = recipe.read_module_role(module_dir)
    except recipe.RecipeParseError as error:
        _note_human(error.message)
        return Outcome.DAE_MODULE_VALIDATE_BAD_ROLE
    if role is not None and role not in _CLOSED_ROLES:
        _note_human(f"invalid role '{role}': not one of {sorted(_CLOSED_ROLES)}.")
        return Outcome.DAE_MODULE_VALIDATE_BAD_ROLE
    return None


def _entry_name(module_dir: Path) -> str | None:
    """The name of the ``@dae.entry`` callable in ``main.py``, or None."""
    main_path = module_dir / "main.py"
    if not main_path.exists():
        # No entry file at all is the missing-entry case, not a crash:
        # spec_from_file_location returns a non-None spec for an absent path, so
        # exec_module would raise FileNotFoundError without this guard.
        return None
    # module_from_spec registers nothing in sys.modules, so the name only labels
    # the loaded object, in its __name__ and in a traceback frame.
    spec = importlib.util.spec_from_file_location(
        f"{module_dir.name}_validate", main_path
    )
    if spec is None or spec.loader is None:
        return None
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    for value in vars(loaded).values():
        if callable(value) and getattr(value, "__daedalus_entry__", False):
            # The intermediate ``str`` annotation pins the Any coming off the
            # dynamically loaded module object (mypy no-any-return).
            name: str = value.__name__
            return name
    return None


def _resolve_module_dir(path: str) -> Path | None:
    """The module dir at ``path`` or ``modules/<path>``, or None when neither is one."""
    for candidate in (Path(path), Path("modules") / path):
        if (candidate / "dae-module.yaml").is_file():
            return candidate
    return None


@module.command("create")
def create(
    module_id: str,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Show what would be created; write nothing."),
    ] = False,
    json_out: JsonOption = False,
) -> None:
    """Scaffold modules/<id>/ with a sound main.py stub and manifest.

    The stub is valid the moment it lands ("dae module validate" passes).
    Refuses to clobber an existing modules/<id>/ (dae.module.create.exists,
    exit 2). --dry-run writes nothing (dae.module.create.dry_run, exit 0).
    """
    target = paths.module_dir(module_id)
    if not paths.is_within_cwd(target):
        raise typer.BadParameter(
            f"module id must stay within the current directory: {module_id!r}"
        )
    would_create = [target / "main.py", target / "dae-module.yaml"]

    if dry_run:
        if not is_json():
            render.preview_banner("module create preview (--dry-run)")
            render.module_create(module_id)
        return resolve(
            Outcome.DAE_MODULE_CREATE_DRY_RUN,
            payload={"paths": [str(p) for p in would_create]},
        )

    if target.exists():
        if not is_json():
            chrome.note(
                f"module '{module_id}' already exists here; refusing to overwrite it."
            )
        return resolve(Outcome.DAE_MODULE_CREATE_EXISTS)

    target.mkdir(parents=True)
    (target / "dae-module.yaml").write_text(_manifest_text())
    (target / "main.py").write_text(_module_stub(module_id))
    if not is_json():
        render.module_create_done(module_id)
        chrome.next_line(f"dae module validate modules/{module_id}")
    return resolve(
        Outcome.MODULE_CREATE_OK, payload={"paths": [str(p) for p in would_create]}
    )


@module.command("try")
def try_(path: str, json_out: JsonOption = False) -> None:
    """Preview the FlowContext one module would receive (runs nothing).

    Shows the input and output paths and ids the module would be handed, so the
    wiring can be checked before a full run. A path that is no module (neither
    <path> nor modules/<path>) is dae.module.try.not_found (exit 2).
    """
    if _resolve_module_dir(path) is None:
        if not is_json():
            chrome.note(
                f"no module found at '{path}' "
                f"(looked at '{path}' and 'modules/{path}')."
            )
        return resolve(Outcome.DAE_MODULE_TRY_NOT_FOUND)
    if not is_json():
        render.module_try(path)
        chrome.note(
            "This previews one module's context in isolation; it runs nothing. "
            "To run the whole lab, use 'dae lab run'."
        )
        chrome.next_line("dae lab run --dry-run")
    return resolve(Outcome.MODULE_TRY_OK)


@module.command("validate")
def validate(path: str, json_out: JsonOption = False) -> None:
    """Check one module has a valid role and a matching @dae.entry; runs no code.

    The first defect, in the order role, entry presence, name match, is its
    dae.module.validate.* failure (exit 1); a sound module is
    dae.module.validate.ok. A path that is no module is not_found (exit 2).
    """
    module_dir = _resolve_module_dir(path)
    if module_dir is None:
        _note_human(
            f"no module found at '{path}' (looked at '{path}' and 'modules/{path}')."
        )
        return resolve(Outcome.DAE_MODULE_VALIDATE_NOT_FOUND)

    role_defect = _role_defect(module_dir)
    if role_defect is not None:
        return resolve(role_defect)

    try:
        entry_name = _entry_name(module_dir)
    except Exception as error:  # noqa: BLE001 (any import-time failure in main.py)
        _note_human(f"main.py raised at import ({type(error).__name__}: {error}).")
        return resolve(Outcome.DAE_MODULE_VALIDATE_MISSING_ENTRY)
    if entry_name is None:
        _note_human("no @dae.entry function found in main.py.")
        return resolve(Outcome.DAE_MODULE_VALIDATE_MISSING_ENTRY)

    if entry_name != module_dir.name:
        _note_human(
            f"entry function '{entry_name}' does not match the module id "
            f"'{module_dir.name}'."
        )
        return resolve(Outcome.DAE_MODULE_VALIDATE_NAME_MISMATCH)

    if not is_json():
        # Count the NotImplementedError markers create/convert plant, so a stub
        # never reads as "none unresolved" while it still raises.
        markers = (module_dir / "main.py").read_text().count("NotImplementedError")
        render.module_validate(path, unresolved_markers=markers)
        chrome.next_line(f"dae module try {path}")
    return resolve(Outcome.MODULE_VALIDATE_OK)


@module.command("convert")
def convert(
    script: str,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Show a preview banner; convert nothing.")
    ] = False,
    json_out: JsonOption = False,
) -> None:
    """Convert a script into a module by scaffolding modules/<id>/ around its body.

    The id comes from the script stem; main.py wraps the body in an @dae.entry
    function with ctx-wiring guidance and runs nothing. A missing script is
    not_found, an existing module exists (both exit 2); --dry-run writes nothing.
    """
    script_path = Path(script)
    if not script_path.is_file():
        if not is_json():
            chrome.note(f"no script found at '{script}'.")
        return resolve(Outcome.DAE_MODULE_CONVERT_NOT_FOUND)

    # The id is sanitized to alnum and underscore, so the target is always a
    # direct child of modules/ in cwd and needs no is_within_cwd guard.
    module_id = _module_id_from_script(script_path)
    target = paths.module_dir(module_id)
    would_create = [target / "main.py", target / "dae-module.yaml"]

    if dry_run:
        if not is_json():
            render.preview_banner("convert preview (--dry-run)")
            render.module_convert_map(script, module_id)
        return resolve(
            Outcome.MODULE_CONVERT_DRY_RUN,
            payload={"paths": [str(p) for p in would_create]},
        )

    if target.exists():
        if not is_json():
            chrome.note(
                f"module '{module_id}' already exists here; refusing to overwrite it."
            )
        return resolve(Outcome.DAE_MODULE_CONVERT_EXISTS)

    target.mkdir(parents=True)
    (target / "dae-module.yaml").write_text(_manifest_text())
    (target / "main.py").write_text(
        _converted_stub(module_id, script_path, script_path.read_text())
    )
    if not is_json():
        render.module_convert_done(script, module_id)
        chrome.next_line(f"dae module validate modules/{module_id}")
    return resolve(
        Outcome.MODULE_CONVERT_OK, payload={"paths": [str(p) for p in would_create]}
    )
