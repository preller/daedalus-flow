"""The Outcome registry stems must match the live Typer command tree.

A code is ``dae.<group>.<command>.<result>``; only the result leaf is hand-written.
"""

from __future__ import annotations

import re

import typer

from daedalus.cli.app import app
from daedalus.core.outcomes import Outcome

# The bare ``dae`` invocation (root callback) prints the onboarding view. Its
# code has no group or command in the tree, so its stem has two segments.
_ROOT_STEM = "onboarding"

# The ``dae.step.*`` codes are a per-step failure taxonomy carried on the
# lineage manifest, not a CLI command result, so they have no command segment.
# The three-segment guard and the orphan guard both admit this group by name.
_STEP_GROUP = "step"

# Groups that are one ``@group.callback`` with no subcommands yet own several
# outcome families keyed by action (`dae example` lists, `dae example NAME`
# scaffolds). Only the group segment is checked against the tree for these.
_CALLBACK_ONLY_GROUPS = {"example"}

# Every code is dotted lowercase, rooted at ``dae.``, with at least one more segment
# after the group/root. Underscores are allowed inside a segment (result leaves like
# ``dry_run`` / ``missing_deps``); the dot is the only segment separator.
_CODE_RE = re.compile(r"^dae\.[a-z]+(?:\.[a-z]+)*(?:\.[a-z][a-z_]*)$")

_ALL_CODES = [str(outcome) for outcome in Outcome]


def _cli_tree() -> dict[str, list[str]]:
    """Top-level group name to sorted subcommand names, from the live Click tree."""
    cli = typer.main.get_command(app)
    tree: dict[str, list[str]] = {}
    for name, command in cli.commands.items():  # type: ignore[attr-defined]
        subcommands = getattr(command, "commands", None)
        tree[name] = sorted(subcommands) if subcommands else []
    return tree


def _stem_parts(code: str) -> tuple[str, str | None]:
    """Split a code into (group, command or None); the result leaf is ignored."""
    parts = code.split(".")
    group = parts[1]
    command = parts[2] if len(parts) >= 4 else None
    return group, command


def test_every_code_is_dae_namespaced_and_well_formed() -> None:
    offenders = [code for code in _ALL_CODES if not _CODE_RE.match(code)]
    assert not offenders, (
        "outcome codes must match dae.<group>.<command>.<result> (dotted lowercase, "
        f"dae.-rooted); offenders: {offenders}"
    )


def test_step_namespace_codes_exist() -> None:
    """The three ``dae.step.*`` codes exist and are FAILURE (exit 1)."""
    from daedalus.core.outcomes import Outcome

    assert str(Outcome.DAE_STEP_LOAD_FAILED) == "dae.step.load_failed"
    assert str(Outcome.DAE_STEP_EXECUTION_FAILED) == "dae.step.execution_failed"
    assert str(Outcome.DAE_STEP_WORKER_FAILED) == "dae.step.worker_failed"
    for code in (
        Outcome.DAE_STEP_LOAD_FAILED,
        Outcome.DAE_STEP_EXECUTION_FAILED,
        Outcome.DAE_STEP_WORKER_FAILED,
    ):
        assert code.exit_code == 1, f"{code} must be a FAILURE (exit 1)"


def test_root_is_the_only_three_segment_code() -> None:
    """Every code but the root and step groups names a group and a command."""
    short = {code for code in _ALL_CODES if code.count(".") == 2}
    allowed = {_ROOT_STEM, _STEP_GROUP}
    assert all(_stem_parts(code)[0] in allowed for code in short), (
        "only the root code and the per-step failure taxonomy may omit a command "
        f"segment; got short codes: {short}"
    )


def test_no_orphan_codes_every_stem_maps_to_a_live_command() -> None:
    """A renamed or removed command leaves its old codes orphaned; this names them."""
    tree = _cli_tree()
    orphans: list[str] = []
    for code in _ALL_CODES:
        group, command = _stem_parts(code)
        if group == _ROOT_STEM:
            continue
        if group == _STEP_GROUP:
            continue  # the per-step taxonomy has no command tree
        if group not in tree:
            orphans.append(f"{code} (group '{group}' is not a CLI group)")
            continue
        if group in _CALLBACK_ONLY_GROUPS:
            continue  # action-keyed family; no subcommand to match
        if command not in tree[group]:
            orphans.append(f"{code} (command '{group} {command}' is not in the tree)")
    assert not orphans, f"outcome codes with no matching command: {orphans}"


def test_every_command_owns_at_least_one_code() -> None:
    """Callback-only groups count at group level; the root counts by its own code."""
    tree = _cli_tree()
    stems = {tuple(_stem_parts(code)) for code in _ALL_CODES}
    groups_seen = {_stem_parts(code)[0] for code in _ALL_CODES}

    missing: list[str] = []
    assert _ROOT_STEM in groups_seen, "the bare 'dae' onboarding view has no code"
    for group, subcommands in tree.items():
        if group in _CALLBACK_ONLY_GROUPS:
            if group not in groups_seen:
                missing.append(f"group '{group}' (callback-only) owns no code")
            continue
        if not subcommands:
            missing.append(
                f"group '{group}' exposes no subcommands and is not known "
                "callback-only; add it to _CALLBACK_ONLY_GROUPS or wire "
                "its commands"
            )
        for command in subcommands:
            if (group, command) not in stems:
                missing.append(f"command 'dae {group} {command}' owns no outcome code")
    assert not missing, "commands without a declared outcome code: " + "; ".join(
        missing
    )
