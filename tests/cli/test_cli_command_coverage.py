"""A command emits only its own code namespace, checked over CONTRACT_CHAINS.

Also pins ``flow resume`` (nothing) and ``module try`` (ok), which no chain covered.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from daedalus.cli.app import app
from tests._helpers import chdir
from tests.cli._cli_contract import CONTRACT_CHAINS, _json_code
from tests.cli.test_outcome_contract import _cli_tree

# Command path -> namespaces it may also emit. The one cross-namespace emitter:
# `dae lab visualize` surfaces the `dae lab validate` verdict when the cwd lab
# cannot be drawn (cli/commands/lab/).
_BORROW: dict[str, set[str]] = {
    "dae.lab.visualize": {"dae.lab.validate"},
}


def _command_namespace(argv: tuple[str, ...]) -> str:
    """The ``dae.<group>.<command>`` namespace an argv invokes; () is onboarding."""
    # Only leading tokens that are tree nodes count: ("example", "minimal") is
    # dae.example, since minimal is the name argument, not a subcommand.
    if not argv:
        return "dae.onboarding"
    tree = _cli_tree()
    parts = ["dae"]
    group = argv[0]
    if group in tree:
        parts.append(group)
        if len(argv) > 1 and argv[1] in tree[group]:
            parts.append(argv[1])
    return ".".join(parts)


def _in_namespace(code: str, namespace: str) -> bool:
    """Whether ``code`` is ``namespace`` or a dotted-segment child of it."""
    return code == namespace or code.startswith(namespace + ".")


def _namespace_ok(argv: tuple[str, ...], code: str) -> bool:
    """Whether ``code`` is in the argv's command namespace or an allowed borrow."""
    namespace = _command_namespace(argv)
    if _in_namespace(code, namespace):
        return True
    return any(
        _in_namespace(code, allowed) for allowed in _BORROW.get(namespace, set())
    )


@pytest.mark.parametrize("argv, expected", CONTRACT_CHAINS)
def test_each_contract_chain_code_is_in_its_command_namespace(
    argv: tuple[str, ...], expected: tuple[int, str]
) -> None:
    """A miswired emission cannot be fixed by pinning a wrong-namespace code."""
    _exit, code = expected
    argv_t = tuple(argv)
    assert _namespace_ok(argv_t, code), (
        f"chain {argv_t} pins code {code!r} outside its command namespace "
        f"{_command_namespace(argv_t)!r}; add to _BORROW only with justification"
    )


def test_namespace_guard_rejects_cross_namespace_and_scopes_the_borrow() -> None:
    """The guard rejects a foreign code and keeps the borrow allowlist scoped."""
    # a command may not claim another command's code
    assert not _namespace_ok(("flow", "status"), "dae.lab.run.ok")
    # the visualize->validate borrow is scoped to visualize, not granted to others
    assert not _namespace_ok(("flow", "status"), "dae.lab.validate.cycle")
    assert _namespace_ok(("lab", "visualize"), "dae.lab.validate.cycle")
    # the in-namespace happy path still passes
    assert _namespace_ok(("lab", "run", "--dry-run"), "dae.lab.run.ok")


def test_flow_resume_nothing_in_empty_cwd(tmp_path: Path) -> None:
    runner = CliRunner()
    with chdir(tmp_path):
        result = runner.invoke(app, ["--json", "flow", "resume"], prog_name="dae")
    assert (result.exit_code, _json_code(result)) == (0, "dae.flow.resume.nothing")


def test_module_try_ok_on_a_created_module(tmp_path: Path) -> None:
    runner = CliRunner()
    with chdir(tmp_path):
        created = runner.invoke(app, ["module", "create", "normalize"], prog_name="dae")
        assert created.exit_code == 0, created.stdout
        result = runner.invoke(
            app, ["--json", "module", "try", "modules/normalize"], prog_name="dae"
        )
    assert (result.exit_code, _json_code(result)) == (0, "dae.module.try.ok")


# --- every command emits a --json envelope; a missing fixture is a failure

# Safe argv (in an empty cwd) that drive each command through resolve() to a
# parseable {code, exit} envelope, whatever the outcome. Keyed by the
# command-path tuple; the bare root is ().
_JSON_FIXTURES: dict[tuple[str, ...], list[str]] = {
    (): [],
    ("example",): ["example"],
    ("lab", "init"): ["lab", "init", "x", "--dry-run"],
    ("lab", "validate"): ["lab", "validate"],
    ("lab", "visualize"): ["lab", "visualize"],
    ("lab", "run"): ["lab", "run", "--dry-run"],
    ("lab", "clean"): ["lab", "clean", "--dry-run"],
    ("module", "create"): ["module", "create", "foo", "--dry-run"],
    ("module", "validate"): ["module", "validate", "ghost"],
    ("module", "try"): ["module", "try", "ghost"],
    ("module", "convert"): ["module", "convert", "no_such.py"],
    ("flow", "status"): ["flow", "status"],
    ("flow", "resume"): ["flow", "resume"],
}


def _required_commands() -> set[tuple[str, ...]]:
    """Every command path that can be run: bare root, callback groups, subcommands."""
    tree = _cli_tree()
    required: set[tuple[str, ...]] = {()}
    for group, subs in tree.items():
        if not subs:
            required.add((group,))  # callback-only group (example)
        for sub in subs:
            required.add((group, sub))
    return required


def test_json_fixture_table_is_complete() -> None:
    """Every command in the live tree has a fixture; a new command fails here."""
    required = _required_commands()
    assert len(required) >= 13, f"introspection returned too few commands: {required}"
    missing = required - set(_JSON_FIXTURES)
    assert not missing, (
        f"commands with no --json fixture (add to _JSON_FIXTURES, never "
        f"skip): {missing}"
    )


@pytest.mark.parametrize("key", sorted(_required_commands()))
def test_command_emits_a_json_envelope(key: tuple[str, ...], tmp_path: Path) -> None:
    """Each command, under --json, emits a parseable {code, exit} envelope."""
    assert key in _JSON_FIXTURES, f"no --json fixture for {key!r}"
    runner = CliRunner()
    with chdir(tmp_path):
        result = runner.invoke(app, ["--json", *_JSON_FIXTURES[key]], prog_name="dae")
    data = json.loads(result.stdout)
    assert isinstance(data.get("code"), str), result.stdout
    assert isinstance(data.get("exit"), int), result.stdout


# --- every command is asserted by a contract row or a documented test file

# Commands whose behavior is pinned outside CONTRACT_CHAINS, with where to find it.
_COVERAGE_EXEMPTIONS: dict[tuple[str, ...], str] = {
    ("flow", "resume"): (
        "resume.nothing in test_cli_command_coverage.py; "
        "ok and failed in test_flow_resume.py"
    ),
}


def _command_tuple(argv: tuple[str, ...]) -> tuple[str, ...]:
    """The command-path tuple an argv invokes (() for the bare root)."""
    namespace = _command_namespace(argv)
    if namespace == "dae.onboarding":
        return ()
    return tuple(namespace.split(".")[1:])


def test_every_command_is_asserted_somewhere() -> None:
    """Each live command appears in CONTRACT_CHAINS or the documented exemption map."""
    required = _required_commands()
    covered = {_command_tuple(tuple(argv)) for argv, _ in CONTRACT_CHAINS}
    uncovered = required - covered - set(_COVERAGE_EXEMPTIONS)
    assert not uncovered, (
        "commands with no test row (add a CONTRACT_CHAINS row or a justified "
        f"_COVERAGE_EXEMPTIONS entry): {uncovered}"
    )
