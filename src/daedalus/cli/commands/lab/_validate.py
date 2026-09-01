"""The recipe-to-Outcome analysis behind the ``dae lab`` commands.

Maps a parsed recipe to its ``dae.lab.validate.*`` or ``dae.lab.run.*``
Outcome, printing the human note on the way, and returns the Outcome or the
sound RecipeSpec. No Typer and no engine. The check order is fixed: structural
``first_defect`` (which catches cycles), then the on-disk role and build_plan
refusals, then the ``core/walks.py`` token-set pass, which needs an acyclic,
role-valid graph.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from daedalus.cli import chrome
from daedalus.cli.commands._outcome import is_json
from daedalus.core import recipe
from daedalus.core.outcomes import Outcome

if TYPE_CHECKING:
    from daedalus.core.engine.isolation import ModuleEnv, ModuleResolution

    _Pairs = list[tuple[ModuleEnv, ModuleResolution]]

# first_defect leaf token -> the dae.lab.validate.* FAILURE outcome it
# maps to. The token is the prefix before the first ":" in the defect string;
# the rest of the string is the human reason chrome.note renders.
_VALIDATE_DEFECT_OUTCOMES: dict[str, Outcome] = {
    "two_emitters": Outcome.DAE_LAB_VALIDATE_TWO_EMITTERS,
    "dangling_dep": Outcome.DAE_LAB_VALIDATE_DANGLING_DEP,
    "cycle": Outcome.DAE_LAB_VALIDATE_CYCLE,
    # Role and structure findings from dag.role_defect, checked after
    # first_defect (cycle) has cleared; first defect only, like the codes above.
    "emitter_not_source": Outcome.DAE_LAB_VALIDATE_EMITTER_NOT_SOURCE,
    "walk_collector_solo": Outcome.DAE_LAB_VALIDATE_WALK_COLLECTOR_SOLO,
    # Walk-model token-pass findings from walks.propagate, checked after
    # role_defect and build_plan have cleared, in the pass's own order
    # (reserved_separator, emitter_multi_successor, token defects, budget).
    "reserved_separator_in_id": Outcome.DAE_LAB_VALIDATE_RESERVED_SEPARATOR_IN_ID,
    "emitter_multi_successor": Outcome.DAE_LAB_VALIDATE_EMITTER_MULTI_SUCCESSOR,
    "collector_incomplete_group": Outcome.DAE_LAB_VALIDATE_COLLECTOR_INCOMPLETE_GROUP,
    "collector_no_walks": Outcome.DAE_LAB_VALIDATE_COLLECTOR_NO_WALKS,
    "walks_reach_flight_collector": (
        Outcome.DAE_LAB_VALIDATE_WALKS_REACH_FLIGHT_COLLECTOR
    ),
    "walk_budget_exceeded": Outcome.DAE_LAB_VALIDATE_WALK_BUDGET_EXCEEDED,
    "config_walk_budget_exceeded": (
        Outcome.DAE_LAB_VALIDATE_CONFIG_WALK_BUDGET_EXCEEDED
    ),
}


def _note_parse_error(error: recipe.RecipeParseError) -> Outcome:
    """Print a parse-error note (human path) and return the parse_error Outcome."""
    if not is_json():
        where = f" (line {error.line})" if error.line is not None else ""
        chrome.note(f"{error.message}{where}")
    return Outcome.DAE_LAB_VALIDATE_PARSE_ERROR


def _note_defect_leaf(finding: str) -> Outcome:
    """Render a defect reason (human path) and map its leaf token to its Outcome."""
    leaf, _, reason = finding.partition(":")
    if not is_json():
        chrome.note(reason.strip())
    return _VALIDATE_DEFECT_OUTCOMES[leaf]


def _note_walk_defect(token: str, reason: str) -> Outcome:
    """Print a walk-model defect reason and map its token to its Outcome."""
    if not is_json():
        chrome.note(reason)
    outcome = _VALIDATE_DEFECT_OUTCOMES.get(token)
    if outcome is None:
        # transform_broadcast_unsupported has no validate code; it rides parse_error.
        return Outcome.DAE_LAB_VALIDATE_PARSE_ERROR
    return outcome


def _recipe_defect_outcome(
    spec: recipe.RecipeSpec, recipe_path: Path
) -> Outcome | None:
    """The validate Outcome of a parsed recipe's first defect, or None when sound."""
    defect = recipe.first_defect(spec)
    if defect is not None:
        return _note_defect_leaf(defect)

    lab_dir = recipe_path.parent
    # Imported here so a bare `dae --help` never pulls networkx;
    # test_engine_lazy_imports.py enforces the lazy import.
    from daedalus.core import dag, walks  # noqa: PLC0415 (lazy: off dae --help)

    try:
        role_finding = dag.role_defect(spec, lab_dir)
        if role_finding is not None:
            return _note_defect_leaf(role_finding)
        recipe.build_plan(spec, lab_dir)
    except recipe.RecipeParseError as error:
        return _note_parse_error(error)

    walk_result = walks.propagate(spec, lab_dir)
    if isinstance(walk_result, walks.WalkDefect):
        return _note_walk_defect(walk_result.token, walk_result.reason)

    return None


def _load_sound_spec(path: str) -> tuple[recipe.RecipeSpec, _Pairs] | Outcome:
    """The sound spec and its isolation pairs at ``path``, or the validate Outcome."""
    recipe_path = Path(path)
    if not recipe_path.is_file():
        if not is_json():
            chrome.note(f"no lab recipe found at '{path}'.")
        return Outcome.DAE_LAB_VALIDATE_NOT_FOUND
    try:
        spec = recipe.load_recipe(recipe_path)
    except recipe.RecipeParseError as error:
        return _note_parse_error(error)

    defect_outcome = _recipe_defect_outcome(spec, recipe_path)
    if defect_outcome is not None:
        return defect_outcome

    # Isolation reconciliation runs last, on a sound role-valid spec: an unbacked
    # preference or nothing-to-nixify is a validate failure; downgrade and
    # auto-generation advisories are non-blocking notes.
    pairs = _lab_resolution_pairs(spec, recipe_path.parent)
    isolation_outcome = _reconcile_isolation(pairs, spec.isolation)
    if isolation_outcome is not None:
        return isolation_outcome

    if not is_json():
        chrome.note(f"Lab recipe at {path} is sound.")
    return spec, pairs


def _validate_recipe_path(path: str) -> Outcome:
    """The Outcome of ``lab validate <path>``, with its human note printed."""
    loaded = _load_sound_spec(path)
    return loaded if isinstance(loaded, Outcome) else Outcome.LAB_VALIDATE_OK


def recipe_summary(spec: recipe.RecipeSpec) -> dict[str, object]:
    """A cheap ``--json`` recipe summary of a sound, already parsed lab.

    The ``modules`` count plus the ``source`` and ``sink`` ids when each is
    unambiguous, read off the parsed spec with no module reads and no walk pass.
    ``walks`` is omitted; the fan-out depends on input rows the recipe cannot know.
    """
    summary: dict[str, object] = {"modules": len(spec.modules)}
    depended_on = {dep for module in spec.modules for dep in module.depends}
    roots = [module.id for module in spec.modules if not module.depends]
    leaves = [module.id for module in spec.modules if module.id not in depended_on]
    if len(roots) == 1:
        summary["source"] = roots[0]
    if len(leaves) == 1:
        summary["sink"] = leaves[0]
    return summary


def _lab_resolution_pairs(
    spec: recipe.RecipeSpec, lab_dir: Path
) -> list[tuple[ModuleEnv, ModuleResolution]]:
    """Each module's (ModuleEnv, ModuleResolution), read from its manifest."""
    from daedalus.core.engine.isolation import (  # noqa: PLC0415 (lazy: off --help)
        ModuleEnv,
        resolve_module,
    )

    pairs = []
    for module in spec.modules:
        env = ModuleEnv.from_module_dir(module.id, lab_dir / "modules" / module.id)
        pairs.append((env, resolve_module(env, spec.isolation, spec.max_workers)))
    return pairs


def isolation_resolution(pairs: _Pairs) -> list[dict[str, object]]:
    """The ``--json`` per-module resolution block of a sound, already parsed lab.

    Each entry carries ``module``, ``strategy``, ``downgraded``, ``source`` and
    ``flake_origin``, read off the pairs the caller resolved; the human render
    and the advisories project from those same pairs.
    """
    return [
        {
            "module": r.module,
            "strategy": r.strategy,
            "downgraded": r.downgraded,
            "source": r.source,
            "flake_origin": r.flake_origin,
        }
        for _env, r in pairs
    ]


def deep_validate(lab_dir: Path, pairs: _Pairs) -> tuple[str, str] | None:
    """Build and import every closure module; return the first failure or None.

    For each module resolved to uv or nix, build its closure and import its entry
    under that env, giving ``(module, cause)`` for the first failure. Ambient
    modules are not probed; the probe imports the entry and never calls it.
    """
    from daedalus.core.engine.isolation import (  # noqa: PLC0415 (lazy: off --help)
        NixProvisionError,
        NixStrategy,
        _module_flake_dir,
    )
    from daedalus.core.engine.subprocess_runner import (  # noqa: PLC0415 (lazy)
        probe_import,
    )

    for _env, resolution in pairs:
        if resolution.strategy not in ("uv", "nix"):
            continue
        module_dir = lab_dir / "modules" / resolution.module
        if resolution.strategy == "nix":
            try:
                NixStrategy().provision(module_dir)
            except NixProvisionError as error:
                return (resolution.module, str(error))
            flake_ref = f"path:{_module_flake_dir(module_dir)}"
            result = probe_import(module_dir, strategy_name="nix", flake_ref=flake_ref)
        else:
            result = probe_import(module_dir, strategy_name="uv")
        if result.status != "completed":
            cause = result.error or result.stderr or "the module entry did not import"
            return (resolution.module, cause.strip())
    return None


def _isolation_error(
    pairs: list[tuple[ModuleEnv, ModuleResolution]], policy: str | None
) -> tuple[Outcome, str] | None:
    """The first reconciliation error (unbacked or nothing-to-nixify), or None."""
    # A nix resolution with no flake_origin is unbacked (nothing-to-nixify under
    # a lab nix policy); a uv preference with no requirements or lock is unbacked.
    for env, r in pairs:
        if r.strategy == "nix" and r.flake_origin is None:
            if policy == "nix":
                return (
                    Outcome.DAE_LAB_VALIDATE_NOTHING_TO_NIXIFY,
                    f"module '{r.module}' is forced to nix (isolation: nix) but "
                    f"ships no flake.nix, uv.lock, or requirements.txt: nothing to "
                    f"nixify. add one, or use isolation: auto or uv.",
                )
            return (
                Outcome.DAE_LAB_VALIDATE_ISOLATION_UNBACKED,
                f"module '{r.module}' prefers nix but ships no flake.nix, uv.lock, "
                f"or requirements.txt to build from. add one, or lower its "
                f"dae-module.yaml isolation preference.",
            )
        if (
            r.strategy == "uv"
            and r.source == "preference"
            and not (env.has_requirements or env.has_lock)
        ):
            return (
                Outcome.DAE_LAB_VALIDATE_ISOLATION_UNBACKED,
                f"module '{r.module}' prefers uv but ships no requirements.txt or "
                f"uv.lock. add one, or lower its dae-module.yaml isolation preference.",
            )
    return None


def _isolation_advisories(pairs: list[tuple[ModuleEnv, ModuleResolution]]) -> list[str]:
    """The non-blocking WARN and INFO notes for a sound lab."""
    notes: list[str] = []
    generated: list[str] = []
    for env, r in pairs:
        if r.downgraded:
            top = env.preference[0]
            notes.append(
                f"WARN: module '{r.module}' prefers {top} but the lab policy runs "
                f"it as {r.strategy}; if it needs {top}-only dependencies the run "
                f"will fail at provisioning (missing_package). raise the lab "
                f"(isolation: auto) or lower the module preference to match."
            )
        if r.flake_origin is not None and r.flake_origin.startswith("generated"):
            generated.append(r.module)
        if env.has_flake and r.strategy != "nix":
            notes.append(
                f"INFO: module '{r.module}' ships a flake.nix but runs as "
                f"{r.strategy}; did you mean isolation: nix?"
            )
    if generated:
        notes.append(
            f"WARN: {len(generated)} module(s) ship no flake.nix, so their nix env "
            f"is auto-generated: {', '.join(generated)}."
        )
    return notes


def _reconcile_isolation(pairs: _Pairs, policy: str | None) -> Outcome | None:
    """Print the isolation advisories and return the first error Outcome, or None."""
    error = _isolation_error(pairs, policy)
    if error is not None:
        outcome, note = error
        return _refuse(outcome, note)
    if not is_json():
        for note in _isolation_advisories(pairs):
            chrome.note(note)
    return None


_VALIDATE_HINT = "try 'dae lab validate' for the detail"

# The one out-of-model walk leaf (core/walks.py) that maps to
# dae.lab.run.unsupported rather than dae.lab.run.invalid: a multi-parent
# broadcast transform, which v1 refuses. Every other WalkDefect is invalid.
_BROADCAST_UNSUPPORTED_TOKEN = "transform_broadcast_unsupported"  # noqa: S105


def _refuse(outcome: Outcome, note: str) -> Outcome:
    """Render a human refusal note (human path only) and return the Outcome."""
    if not is_json():
        chrome.note(note)
    return outcome


def _walk_model_run_defect(spec: recipe.RecipeSpec, lab_dir: Path) -> Outcome | None:
    """The run refusal for a lab the walk engine cannot run, or None if runnable."""
    # Imported here so a bare `dae --help` never pulls networkx
    # (test_engine_lazy_imports.py enforces the lazy import).
    from daedalus.core import dag, walks  # noqa: PLC0415 (lazy: off dae --help)

    # Role and walk-model defects are invalid (exit 2, pointing at validate);
    # the out-of-model broadcast leaf is unsupported.
    try:
        role_finding = dag.role_defect(spec, lab_dir)
    except recipe.RecipeParseError as error:
        # A bad module dir / missing or out-of-set role: refuse before any run.
        return _refuse(
            Outcome.DAE_LAB_RUN_INVALID, f"{error.message} ({_VALIDATE_HINT})."
        )
    if role_finding is not None:
        _, _, reason = role_finding.partition(":")
        return _refuse(
            Outcome.DAE_LAB_RUN_INVALID, f"{reason.strip()} ({_VALIDATE_HINT})."
        )

    walk_result = walks.propagate(spec, lab_dir)
    if isinstance(walk_result, walks.WalkDefect):
        if walk_result.token == _BROADCAST_UNSUPPORTED_TOKEN:
            return _refuse(Outcome.DAE_LAB_RUN_UNSUPPORTED, walk_result.reason)
        return _refuse(
            Outcome.DAE_LAB_RUN_INVALID,
            f"{walk_result.reason} ({_VALIDATE_HINT}).",
        )
    return None


def _load_runnable_spec(lab_path: Path) -> recipe.RecipeSpec | Outcome:
    """The runnable spec at ``lab_path``, or its refusal Outcome (note printed)."""
    # first_defect (which catches cycles) runs before the walk pass, which
    # assumes an acyclic graph; an empty spec is invalid, not unsupported.
    try:
        spec = recipe.load_recipe(lab_path)
    except recipe.RecipeParseError as error:
        where = f" (line {error.line})" if error.line is not None else ""
        return _refuse(
            Outcome.DAE_LAB_RUN_INVALID,
            f"this lab does not parse{where}: {error.message} ({_VALIDATE_HINT}).",
        )

    if not spec.modules:
        return _refuse(
            Outcome.DAE_LAB_RUN_INVALID, "this lab declares no modules to run."
        )

    defect = recipe.first_defect(spec)
    if defect is not None:
        _, _, reason = defect.partition(":")
        return _refuse(
            Outcome.DAE_LAB_RUN_INVALID, f"{reason.strip()} ({_VALIDATE_HINT})."
        )

    refusal = _walk_model_run_defect(spec, lab_path.parent)
    if refusal is not None:
        return refusal
    return spec
