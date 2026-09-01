"""Every fixed string the CLI prints.

Each builder is a pure string function: it reads nothing, writes nothing and
echoes only its name, path or script argument back into the text. The lab
name, flow id and recipe come from ``topology.py``. Mutating verbs in a preview
say what they would do, and every preview run verb ends with
``NOTHING_EXECUTED``. Plain ASCII punctuation, American English.
"""

from daedalus.core import topology

ROOT_TAGLINE = (
    "daedalus (dae) - design, validate, and run labs of modules: "
    "reproducible analysis pipelines for data-intensive science."
)

# Global-option help, kept here so the root callback and the shared per-leaf
# --json option read one string (the flag works in any position; one help text).
JSON_OPTION_HELP = "Emit machine-readable JSON to stdout."
VERSION_OPTION_HELP = "Show the dae version and exit."

# Examples gallery

# The example names, simplest first; keys match _EXAMPLE_DESC. demo stays last
# as the reference Lab and complex sits before it as the advanced shape.
KNOWN_EXAMPLES: list[str] = [
    "minimal",
    "ensemble",
    "parallel",
    "isolation-nix",
    "complex",
    "demo",
]

# The subset of KNOWN_EXAMPLES that has a real bundle to scaffold. Every known
# example ships a bundle today; a new ladder entry lands here only when its
# bundle does. This is the single source the example command reads too.
AVAILABLE_EXAMPLES: list[str] = list(KNOWN_EXAMPLES)

# The post-scaffold Next hint per example. The journey tier runs these lines
# verbatim, so they chain validate and visualize before a dry-run and start
# no real run (isolation-nix needs nix; demo and ensemble are slow).
_SCAFFOLD_CHAIN = "dae lab validate && dae lab visualize && dae lab run --dry-run"
NEXT_AFTER_SCAFFOLD: dict[str, str] = {
    name: f"cd {name} && {_SCAFFOLD_CHAIN}"
    for name in ("minimal", "ensemble", "parallel", "isolation-nix", "complex", "demo")
}

# Post-scaffold pointer at the input/ dir, printed when the scaffolder finds
# one on disk. {input_file} is .format()-interpolated with the file it found.
INPUT_DIR_HINT = "edit {input_file} with your own input data, then run the lab."

_EXAMPLE_DESC: dict[str, str] = {
    "minimal": "one module, one step - the smallest Lab that runs",
    "ensemble": "one input fanned across many targets",
    "parallel": "branches that run side by side, then a barrier join",
    "isolation-nix": "per-module nix envs, proven by two pinned library versions",
    "complex": "nested and sibling collectors in several regions, a token-solo join",
    "demo": "the full exo-survey reference Lab (the one these examples build on)",
}

# The two preview lines every dry-run and try ends with.
NOTHING_EXECUTED = "nothing was executed (preview only)"
PREVIEW_ONLY = "(preview only - nothing was written)"

# The dry-run plan preview writes nothing; flow status only reads the lineage.
DRY_RUN_NO_WRITE = "nothing was written (--dry-run shows the plan only)"
STATUS_READ_ONLY = "status is read-only; it never changes a flow."
# Label for the per-flow results copy line, printed after a
# completed run beside the lineage path. The path is interpolated by render.py.
RESULTS_LABEL = "results: "

# Legend for the visualize walk-line glyphs. The node table has its own E/T/W/F
# legend (render._base._role_legend); the walk lines need a second key, with
# the same "legend:" prefix.
WALK_GLYPH_LEGEND = "legend:  {} branch   () walk-collector   [] flight-collector"

# The runtime unit word. The static recipe counts "modules"; a run fans each
# fanned module across its input rows into per-walk step instances. The run
# and status surfaces name that unit rather than overloading "step".
STEP_INSTANCE = "step instance"

# Missing third-party dep guidance (dae.lab.run.missing_deps). The caller
# .format()s module_id and pkg; chrome.note prints the newlines verbatim. The
# contract test pins "max_workers" present and "future feature" absent.
MISSING_DEPS_HINT = (
    "module '{module_id}' needs the '{pkg}' package, but it is not installed in "
    "the Python environment you are running dae from.\n"
    "At the default 'max_workers: 1', daedalus runs every module in that one "
    "shared environment, so each module's dependencies must already be installed "
    "there.\n"
    "Two ways to fix it:\n"
    "  1. Install it yourself, then run again:\n"
    "       pip install {pkg}\n"
    "     (or install the module's whole list: "
    "pip install -r modules/{module_id}/requirements.txt)\n"
    "  2. Let daedalus isolate each module for you: set 'max_workers: 2' in "
    "lab.yaml. daedalus then runs each module in its own environment and installs "
    "the packages from its requirements.txt automatically.\n"
    "Either way, make sure '{pkg}' is listed in "
    "modules/{module_id}/requirements.txt."
)

# engine_unavailable (FAILURE, exit 1): the lab set engine: prefect but the
# optional PrefectEngine backend is not installed. Names the install path.
ENGINE_UNAVAILABLE_HINT = (
    "lab.yaml sets engine: prefect, but the optional Prefect engine is not "
    "importable by the dae you are running. install it with: pip install "
    "daedalus-flow[engine], or with uv: uv sync --extra engine. then run dae from "
    "that same environment. a dae from a different install will not see the extra, "
    "so use 'uv run dae ...' or activate that venv. otherwise run the lab on the "
    "default in-process engine by setting engine: local in lab.yaml."
)

# isolation_unavailable (FAILURE, exit 1): the lab set isolation: nix but the
# nix backend cannot run on this host. Names the prerequisite (a build-capable
# nix) and the fallback (drop the field); the run does not fall back to uv.
ISOLATION_UNAVAILABLE_HINT = (
    "lab.yaml sets isolation: nix, but a build-capable nix is not usable by the "
    "dae you are running. nix is a host prerequisite, not a pip dep. install nix "
    "with flakes enabled, then run dae again. flakes need a multi-user daemon and "
    "a writable store, or a host whose kernel allows nix's sandbox. otherwise drop the "
    "isolation: field (or set isolation: uv) in lab.yaml to use the uv backend."
)


# Plain validate never builds; when a module resolves to a closure strategy
# (uv or nix) this one line points at --deep, which builds and import-checks
# every closure before a run.
def validate_deep_nudge(count: int) -> str:
    """The one-line plain-validate nudge toward --deep for ``count`` closure modules."""
    noun = "module needs" if count == 1 else "modules need"
    return (
        f"{count} {noun} closure builds; run 'dae lab validate --deep' to build "
        f"and import-check them before running."
    )


VALIDATE_DEEP_HELP = (
    "Build every module's isolation closure up front and dry-run-import each "
    "module entry. Fail fast if a closure will not build or a module will not "
    "import, before any science runs."
)

# Human-mode notes after a prefect run; {flow_id} and {url} are .format()-
# interpolated. The Prefect UI needs a running server, so the notes point at
# PREFECT_API_URL when it is set or print the start recipe. Never under --json.

# Printed before the lazy prefect import, which takes a few seconds.
PREFECT_STARTING = (
    "starting the Prefect engine (first run boots Prefect, a few seconds)..."
)
PREFECT_ENGINE_NOTE = "ran on the Prefect engine (flow {flow_id})."
PREFECT_UI_LIVE = (
    "watch it in the Prefect UI: {url} (open the latest flow run for this lab)."
)
PREFECT_UI_HINT = (
    "to watch runs in the Prefect UI, start a server (prefect server start), then "
    "set PREFECT_API_URL=http://127.0.0.1:4200/api and run again."
)

# Footer for a local run at max_workers 1, where every step runs one at a time.
# It names both concurrency paths and says "steps", not "branches", so it also
# holds for a lab with no parallel branches. Human surface only.
SERIAL_RUN_NOTE = (
    "ran serially on the local engine (max_workers 1): steps ran one at a "
    "time. for concurrency, set max_workers > 1 in lab.yaml or use the prefect "
    "engine (engine: prefect)."
)

# The lab validate structure reasons (emitter_not_source, walk_collector_solo,
# cycle, dangling_dep, two_emitters) are built in core next to the checks that
# own the ids; core cannot import cli.

# Usage examples, one invocation per command; a CliRunner test parses them back.
USAGE_EXAMPLES: dict[str, str] = {
    "example": "dae example minimal",
    "lab init": "dae lab init exo-survey",
    "lab validate": "dae lab validate",
    "lab visualize": "dae lab visualize",
    "lab run": "dae lab run --dry-run",
    "module create": "dae module create normalize",
    "module try": "dae module try modules/fit_nested",
    "module validate": "dae module validate modules/fit_nested",
    "module convert": "dae module convert legacy_fit.py",
    "flow status": "dae flow status",
    "flow resume": "dae flow resume",
}


def _basename(path: str) -> str:
    """The trailing module name of a path; empty falls back to the source node."""
    return path.rstrip("/").rsplit("/", 1)[-1] or topology.source()


# Front door

# The bare `dae` onboarding text as data, so render.py lays it out as a grid.
# `dae example minimal` comes first, then `dae lab init <name>`.
ONBOARDING_WAYS_LABEL = "New here? Two ways in:"

ONBOARDING_WAYS: list[tuple[str, str]] = [
    ("dae example minimal", "scaffold the smallest Lab and read it"),
    ("dae lab init <name>", "start your own Lab from scratch"),
]

ONBOARDING_HELP_HINT = "Run 'dae <command> --help' for details."


def commands_line(groups: list[str]) -> str:
    """The command listing line, generated from the registered groups."""
    return "Commands: " + " - ".join(groups)


# example

EXAMPLE_LADDER_HEADER = "Example ladder (simplest first):"


def example_rows() -> list[tuple[str, str]]:
    """The ``dae example`` ladder as (name, description) rows, simplest first.

    The top example is tagged as the reference Lab so a reader knows where the
    ladder ends. render.py lays these out as a command grid.
    """
    rows = []
    for name in KNOWN_EXAMPLES:
        tag = "  (the reference)" if name == KNOWN_EXAMPLES[-1] else ""
        rows.append((name, f"{_EXAMPLE_DESC[name]}{tag}"))
    return rows


# lab


def lab_init(name: str) -> str:
    """``dae lab init <name>``: a would-create preview of a fresh Lab skeleton."""
    return "\n".join(
        [
            f"would create a new Lab '{name}'",
            f"  would create {name}/lab.yaml      (the Lab manifest)",
            f"  would create {name}/modules/      (one folder per module)",
            "",
            f"  then add a module:  cd {name} && dae module create my_step",
            "",
            PREVIEW_ONLY,
        ]
    )


def lab_init_done(name: str) -> str:
    """``dae lab init <name>``: the summary after the Lab was written.

    Past tense and no preview banner, since this runs only on the real-write path.
    """
    return "\n".join(
        [
            f"created a new Lab '{name}'",
            f"  created {name}/lab.yaml      (the Lab manifest)",
            f"  created {name}/modules/      (one folder per module)",
            f"  created {name}/{topology.INTERNAL_DIR}/   (daedalus internal state)",
            "",
            f"  then add a module:  cd {name} && dae module create my_step",
        ]
    )


# module

# The role comment a generated dae-module.yaml carries, the same one the bundled
# minimal example's manifest uses. module.py writes it beside the role scalar.
MODULE_ROLE_COMMENT = (
    "# role: how this module fans data out and is gathered "
    "(transform | emitter | walk_collector | flight_collector). see the roles doc."
)

# The ctx read/write snippet, transcribed from examples/minimal/modules/normalize:
# read one named file from the input dir, write one into the output dir. Printed
# by convert and pasted into the generated main.py as a comment; plain text.
CTX_WIRING_SNIPPET: tuple[str, str, str] = (
    'rows = (ctx.step_input_path / "raw.csv").read_text()  # read your input',
    "result = ...  # your analysis here",
    '(ctx.step_output_path / "result.json").write_text(result)  # write your output',
)

# Post-convert hint pointing at the wrap-into-a-lab step. convert writes a
# bare modules/<id>/ with no obvious "now make this runnable" path; this names
# the lab-init wrap step (a hint only; no new flag is added here).
CONVERT_WRAP_HINT = (
    "to run this module, wrap it in a lab: dae lab init <name> "
    "(then move modules/{module_id} under it, or convert inside a lab dir)."
)


def module_create(module_id: str) -> str:
    """``dae module create <id>``: a would-create preview of a module folder."""
    return "\n".join(
        [
            f"would create module '{module_id}'",
            f"  would create modules/{module_id}/main.py      "
            f"(an @dae.entry function to fill in)",
            f"  would create modules/{module_id}/dae-module.yaml  "
            f"(role: transform by default)",
            "",
            f"  then validate it:  dae module validate modules/{module_id}",
            "",
            PREVIEW_ONLY,
        ]
    )


def module_create_done(module_id: str) -> str:
    """``dae module create <id>``: the summary after the module was written.

    Past tense and no preview banner, since this runs only on the real-write
    path. The stub passes ``dae module validate`` clean.
    """
    return "\n".join(
        [
            f"created module '{module_id}'",
            f"  created modules/{module_id}/main.py      "
            f"(an @dae.entry function to fill in)",
            f"  created modules/{module_id}/dae-module.yaml  (role: transform)",
            "",
            f"  then validate it:  dae module validate modules/{module_id}",
        ]
    )


TRY_CONTEXT_LABEL = "it would receive this FlowContext:"
TRY_NOTE = "one invocation, no Lab, no fan-out."


def try_intro(path: str) -> str:
    """The ``module try`` intro line.

    ``try`` previews the FlowContext one module would receive and runs nothing;
    the copy says "preview", not "smoke test". ``path`` is interpolated with an
    f-string, so braces in it are harmless.
    """
    return f"preview: {path}   (the context one module would receive; nothing runs)"


def module_try_context(path: str) -> list[tuple[str, str]]:
    """The single FlowContext ``dae module try`` would hand the module.

    Returned as (field, value) rows. The sandbox path uses the
    ``dae-outputs/try/`` convention; render.py lays the rows out as
    a kv grid.
    """
    name = _basename(path)
    role = topology.role_of(name)
    sandbox = topology.try_path(name)
    return [
        ("step_id", name),
        ("role", str(role)),
        ("step_input_path", f"{sandbox}input/   (sample data)"),
        ("step_output_path", f"{sandbox}output/  (would be written here)"),
        ("flight_id", "flight_1"),
        ("walk_id", "walk_1"),
        ("seed", "0"),
    ]


def module_validate_rows(
    path: str, unresolved_markers: int = 0
) -> list[tuple[str, str]]:
    """The structural report for one module, as (field, value) rows.

    The role word is spelled out; the "check" row says the check is structure
    only and does not run the code. ``unresolved_markers`` is the count of
    ``NotImplementedError`` markers found in main.py, reported as scanned.
    """
    name = _basename(path)
    role = topology.role_of(name)
    markers = (
        "none unresolved"
        if unresolved_markers == 0
        else f"{unresolved_markers} unresolved (NotImplementedError)"
    )
    return [
        ("entry", "@dae.entry found"),
        ("role", str(role)),
        ("markers", markers),
        ("check", "structure only (does not run your code)"),
    ]


def module_convert(script: str, module_id: str) -> str:
    """``dae module convert <script> --dry-run``: the would-convert preview.

    convert scaffolds ``modules/<id>/`` and pastes the script body into an
    ``@dae.entry`` function. It infers no inputs, outputs or dependencies and
    never runs the module; nothing is written on this path.
    """
    dest = f"modules/{module_id}"
    return "\n".join(
        [
            f"would convert {script} into {dest}/",
            f"  would write {dest}/main.py            "
            "(the script body wrapped in an @dae.entry function)",
            f"  would write {dest}/dae-module.yaml    (role: transform)",
            "",
            "  you would then wire ctx.step_input_path / ctx.step_output_path in "
            "main.py, e.g.:",
            *(f"      {line}" for line in CTX_WIRING_SNIPPET),
            f"  then validate it:  dae module validate {dest}",
            f"  {CONVERT_WRAP_HINT.format(module_id=module_id)}",
            "",
            PREVIEW_ONLY,
        ]
    )


def module_convert_done(script: str, module_id: str) -> str:
    """``dae module convert <script>``: the summary after the module is written.

    Past tense and no preview banner. The written module passes ``dae module
    validate`` clean; the pasted body still needs its ctx paths wired.
    """
    dest = f"modules/{module_id}"
    return "\n".join(
        [
            f"converted {script} into {dest}/",
            f"  created {dest}/main.py            "
            "(the script body wrapped in an @dae.entry function)",
            f"  created {dest}/dae-module.yaml    (role: transform)",
            "",
            "  then wire ctx.step_input_path / ctx.step_output_path in main.py, e.g.:",
            *(f"      {line}" for line in CTX_WIRING_SNIPPET),
            f"  then validate it:  dae module validate {dest}",
            f"  {CONVERT_WRAP_HINT.format(module_id=module_id)}",
        ]
    )


# Walk-model validate refusals, wired into dae lab validate. The token pass in
# core has no cli dependency, so the human text lives here.

# collector_incomplete_group: the incoming token group is a partial or
# cross-brancher set. The caller .format()s collector_id, got (the actual
# token set) and expected (the required set).
WALK_COLLECTOR_INCOMPLETE_GROUP = (
    "module '{collector_id}' is a walk_collector whose incoming walk tokens "
    "{got!r} do not form a complete branch set. expected exactly {expected!r} "
    "(all siblings from one brancher). fix: ensure the collector's parents are "
    "the full sibling set produced by a single brancher, with no cross-brancher "
    "or cross-level merges."
)

# collector_no_walks: the collector sees only the parent (root) token, nothing
# to merge. The caller .format()s collector_id.
WALK_COLLECTOR_NO_WALKS = (
    "module '{collector_id}' is a walk_collector but receives no walk tokens "
    "(only the root / parent token flows in). a walk_collector must merge at "
    "least two parallel walk tokens. fix: verify the upstream brancher produces "
    "walk tokens that reach this collector, or remove the collector if no "
    "branching occurs upstream."
)

# walks_reach_flight_collector: a non-root walk token reaches the flight sink.
# The caller .format()s collector_id and token.
WALK_WALKS_REACH_FLIGHT_COLLECTOR = (
    "walk token {token!r} flows into the flight_collector '{collector_id}'. "
    "in v1 the flight_collector must receive only the flight root token; "
    "parallel walks must be resolved by a walk_collector before the flight "
    "sink. fix: add a walk_collector to converge the parallel walks before "
    "'{collector_id}'."
)

# emitter_multi_successor: the emitter fans out to two or more successors.
# The caller .format()s emitter_id and count.
WALK_EMITTER_MULTI_SUCCESSOR = (
    "module '{emitter_id}' is an emitter with {count} successors. the flight "
    "template requires a single root walk, so the emitter must have exactly "
    "one successor. fix: insert a transform between the emitter and its "
    "successors so only one edge leaves the emitter."
)

# walk_budget_exceeded: instance count over the per-flight budget. The caller
# .format()s count and budget.
WALK_BUDGET_EXCEEDED = (
    "the token-set pass produced {count} walk instances but the per-flight "
    "budget is {budget}. daedalus does not truncate walks: raise the walk "
    "budget or reduce branching."
)

# reserved_separator_in_id: a module id contains '@'. The caller .format()s
# module_id.
WALK_RESERVED_SEPARATOR_IN_ID = (
    "module id '{module_id}' contains '@', which is reserved for instance ids "
    "('<module>@w<id>'). a '@' in a module id makes instance ids ambiguous and "
    "prevents injective mapping to filesystem directories. fix: rename the "
    "module, removing the '@' character."
)
