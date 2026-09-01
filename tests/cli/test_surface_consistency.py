"""The ``exit`` an outcome carries agrees with what its code claims, both ways.

Code grammar and envelope presence are covered by the outcome and coverage tests.
"""

from __future__ import annotations

import json
import tempfile

from typer.testing import CliRunner

from daedalus.cli.app import app
from daedalus.core.outcomes import Outcome
from tests._helpers import chdir
from tests.cli.test_cli_command_coverage import _JSON_FIXTURES, _required_commands

# Result leaves whose name makes a hard claim about success or failure, with
# the exit each claim requires. Ambiguous leaves (nothing, exists, not_found)
# are left out; their OK or USAGE classing is a judgment call.
_SUCCESS_LEAVES = {"ok", "dry_run"}  # exit 0
_FAILURE_LEAVES = {"failed"}  # exit != 0

# Code-string -> member. ``Outcome(code)`` works at runtime but mypy reads the
# custom ``__new__(code, category)`` as a 2-arg constructor, so resolve via a map.
_BY_CODE = {str(outcome): outcome for outcome in Outcome}


def _leaf(code: str) -> str:
    return code.rsplit(".", 1)[-1]


def _leaf_contradicts_exit(leaf: str, exit_code: int) -> bool:
    """True if a leaf's success/failure claim contradicts its exit code."""
    if leaf in _SUCCESS_LEAVES:
        return exit_code != 0
    if leaf in _FAILURE_LEAVES:
        return exit_code == 0
    return False


def test_leaf_contradicts_exit_catches_a_planted_violation() -> None:
    """The predicate catches a planted violation, so a pass below means something."""
    assert _leaf_contradicts_exit("ok", 1), "an .ok leaf at exit 1 contradicts its exit"
    assert _leaf_contradicts_exit("failed", 0), (
        "a .failed leaf at exit 0 contradicts its exit"
    )
    assert not _leaf_contradicts_exit("ok", 0)
    assert not _leaf_contradicts_exit("failed", 1)
    assert not _leaf_contradicts_exit("nothing", 0), (
        "ambiguous leaves are not policed here"
    )


def test_registry_leaf_agrees_with_exit() -> None:
    """No registry code claims ok or dry_run while exiting nonzero (invariant A)."""
    offenders = [
        (str(outcome), outcome.exit_code)
        for outcome in Outcome
        if _leaf_contradicts_exit(_leaf(str(outcome)), outcome.exit_code)
    ]
    assert not offenders, (
        "outcome codes must not contradict their exit: an .ok/.dry_run code must "
        f"exit 0 and a .failed code must exit nonzero; offenders: {offenders}"
    )


def test_live_envelope_exit_matches_registry() -> None:
    """Each command's emitted exit equals the registry exit and the process exit."""
    runner = CliRunner()
    for key in sorted(_required_commands()):
        argv = _JSON_FIXTURES[key]
        with tempfile.TemporaryDirectory() as d, chdir(d):
            result = runner.invoke(app, ["--json", *argv], prog_name="dae")
        data = json.loads(result.stdout)
        code, emitted_exit = data["code"], data["exit"]
        expected = _BY_CODE[code].exit_code
        assert emitted_exit == expected, (
            f"{key}: envelope exit {emitted_exit} != registry {expected} for {code}"
        )
        assert result.exit_code == emitted_exit, (
            f"{key}: process exit {result.exit_code} != envelope {emitted_exit}"
        )
