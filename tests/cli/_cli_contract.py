"""Helpers and constants for the ``test_cli_contract_*.py`` family.

Tests assert on (exit code, ``--json`` code) and file effects, not on rendered text.
"""

from __future__ import annotations

import contextlib
import json
import tempfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from daedalus.cli.app import app
from tests._helpers import _copy_lab as _copy_fixture_lab
from tests._helpers import chdir, fixtures_root
from tests.core.engine._local_engine import _flows_root as _flows_dir
from tests.core.engine._local_engine import _only_flow

# Re-exported under the names the contract suites import from here.
__all__ = ["_copy_fixture_lab", "_flows_dir", "_only_flow"]

OK_EXIT = 0
FAILURE_EXIT = 1
USAGE_EXIT = 2

_BROKEN_MODULES = fixtures_root() / "broken_modules"
_BROKEN_LABS = fixtures_root() / "broken_labs"
_FIXTURE_LABS = fixtures_root() / "labs"

# The `lab run` / `flow status` chains below pin the contract (exit code, json code,
# and the observable filesystem effect) of the real serial engine.


def _run_cli_in(path: Path, *args: str) -> tuple[int, str | None]:
    """Invoke the app under ``--json`` with cwd set to ``path``; return (exit, code)."""
    runner = CliRunner()
    with chdir(path):
        result = runner.invoke(app, ["--json", *args], prog_name="dae")
    return result.exit_code, _json_code(result)


@contextlib.contextmanager
def _isolated_cwd():
    """Run the body in a temporary cwd; CliRunner has no isolated_filesystem here."""
    with tempfile.TemporaryDirectory() as tmp, chdir(tmp):
        yield tmp


@pytest.fixture(autouse=True)
def _reset_json_state():
    """Reset the process-global ``_outcome.state["json"]`` flag around every test."""
    from daedalus.cli.commands._outcome import state

    state["json"] = False
    yield
    state["json"] = False


@pytest.fixture
def runner() -> CliRunner:
    """A plain ``CliRunner`` (streams split automatically on this Typer).

    Most tests call the module-level :func:`run_cli` helper, which builds its own
    runner per call. This fixture exists for the few contracts that need several
    invocations to share one isolated cwd (for example ``lab init`` run twice).
    """
    return CliRunner()


def _json_code(result) -> str | None:
    """The ``code`` field of a ``--json`` result; ``None`` when stdout was not JSON."""
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    return data["code"]  # a missing key propagates as KeyError


def run_cli(*args: str) -> tuple[int, str | None]:
    """Invoke the dae app under ``--json``; return ``(exit_code, json code)``.

    The global ``--json`` flag lives on the root callback, so it leads the argv.
    The call runs in an isolated filesystem so any writes from the mutating
    ``lab init`` / ``lab clean`` verbs stay hermetic.
    """
    runner = CliRunner()
    with _isolated_cwd():
        result = runner.invoke(app, ["--json", *args], prog_name="dae")
    return result.exit_code, _json_code(result)


# Every in-scope command chain, asserted against the contract table and the
# outcome catalog. `lab visualize` takes no path argument, so its chain is the
# bare command.
CONTRACT_CHAINS = [
    ((), (OK_EXIT, "dae.onboarding.ok")),
    (("example",), (OK_EXIT, "dae.example.list.ok")),
    (("example", "minimal"), (OK_EXIT, "dae.example.scaffold.ok")),
    (("example", "zzz"), (USAGE_EXIT, "dae.example.scaffold.not_found")),
    (("lab", "visualize"), (OK_EXIT, "dae.lab.visualize.ok")),
    # In run_cli's empty cwd there is no lab.yaml and no dae-outputs/flows/, so
    # `lab run --dry-run` is the not_found refusal (exit 2) and `flow status` is
    # the empty-query nothing (exit 0). Real runs are pinned by the run tests.
    (("lab", "run", "--dry-run"), (USAGE_EXIT, "dae.lab.run.not_found")),
    (("flow", "status"), (OK_EXIT, "dae.flow.status.nothing")),
    # `module validate` resolves each broken fixture to its FAILURE code (exit 1):
    # an out-of-set role, an undecorated entry, an entry name that does not
    # match the directory id.
    (
        ("module", "validate", str(_BROKEN_MODULES / "bad_role")),
        (FAILURE_EXIT, "dae.module.validate.bad_role"),
    ),
    (
        ("module", "validate", str(_BROKEN_MODULES / "missing_entry")),
        (FAILURE_EXIT, "dae.module.validate.missing_entry"),
    ),
    (
        ("module", "validate", str(_BROKEN_MODULES / "name_mismatch")),
        (FAILURE_EXIT, "dae.module.validate.name_mismatch"),
    ),
    # A module dir with a valid manifest but no main.py reports missing_entry
    # rather than crashing on the absent file.
    (
        ("module", "validate", str(_BROKEN_MODULES / "no_main")),
        (FAILURE_EXIT, "dae.module.validate.missing_entry"),
    ),
    # A main.py that raises at import reports missing_entry, never a traceback.
    (
        ("module", "validate", str(_BROKEN_MODULES / "raises_on_import")),
        (FAILURE_EXIT, "dae.module.validate.missing_entry"),
    ),
    # real `lab validate <path>` resolves each broken recipe to
    # its FAILURE code (exit 1): a cycle in the depends graph, a depend on an
    # undeclared id, and more than one declared emitter.
    (
        ("lab", "validate", str(_BROKEN_LABS / "cyclic.yaml")),
        (FAILURE_EXIT, "dae.lab.validate.cycle"),
    ),
    (
        ("lab", "validate", str(_BROKEN_LABS / "dangling_dep.yaml")),
        (FAILURE_EXIT, "dae.lab.validate.dangling_dep"),
    ),
    (
        ("lab", "validate", str(_BROKEN_LABS / "two_emitters.yaml")),
        (FAILURE_EXIT, "dae.lab.validate.two_emitters"),
    ),
    # A dangling dependency written in block-style YAML (a `- item`
    # list under `depends:`) must be caught too, not silently dropped by the
    # hand-rolled parser. Pins the block-style path against a false OK.
    (
        ("lab", "validate", str(_BROKEN_LABS / "block_dangling.yaml")),
        (FAILURE_EXIT, "dae.lab.validate.dangling_dep"),
    ),
    # A validate path that points at no module / no recipe is a
    # clean not_found usage error (exit 2), never a raw FileNotFoundError traceback.
    # In run_cli's isolated empty cwd, neither "ghost" nor "modules/ghost" exists.
    (("module", "validate", "ghost"), (USAGE_EXIT, "dae.module.validate.not_found")),
    (("lab", "validate", "nope.yaml"), (USAGE_EXIT, "dae.lab.validate.not_found")),
    # The path-taking verbs must not claim success on a missing input.
    (("module", "try", "ghost"), (USAGE_EXIT, "dae.module.try.not_found")),
    (("module", "convert", "no_such.py"), (USAGE_EXIT, "dae.module.convert.not_found")),
    # Both sound labs validate clean. linear_smoke passes since summarize_walk
    # was re-roled from walk_collector to transform, which took it out of the
    # walk_collector_solo rule.
    (
        ("lab", "validate", str(_FIXTURE_LABS / "exoplanet_validation" / "lab.yaml")),
        (OK_EXIT, "dae.lab.validate.ok"),
    ),
    (
        ("lab", "validate", str(_FIXTURE_LABS / "linear_smoke" / "lab.yaml")),
        (OK_EXIT, "dae.lab.validate.ok"),
    ),
    # emitter_not_source keys on the lab.yaml role; walk_collector_solo keys on
    # the on-disk dae-module.yaml role; flight_collector_source reuses the
    # build_plan collector-as-source refusal through the parse_error sink.
    (
        ("lab", "validate", str(_BROKEN_LABS / "emitter_not_source" / "lab.yaml")),
        (FAILURE_EXIT, "dae.lab.validate.emitter_not_source"),
    ),
    (
        ("lab", "validate", str(_BROKEN_LABS / "walk_collector_solo" / "lab.yaml")),
        (FAILURE_EXIT, "dae.lab.validate.walk_collector_solo"),
    ),
    (
        (
            "lab",
            "validate",
            str(_BROKEN_LABS / "flight_collector_source" / "lab.yaml"),
        ),
        (FAILURE_EXIT, "dae.lab.validate.parse_error"),
    ),
    # --dry-run previews short-circuit before any write (exit 0).
    (("lab", "init", "x", "--dry-run"), (OK_EXIT, "dae.lab.init.dry_run")),
    (("module", "create", "foo", "--dry-run"), (OK_EXIT, "dae.module.create.dry_run")),
    # lab clean --dry-run previews and removes nothing (exit 0).
    # In the isolated empty cwd run_cli provides, there is nothing to remove, but
    # a dry-run is always the preview outcome.
    (("lab", "clean", "--dry-run"), (OK_EXIT, "dae.lab.clean.dry_run")),
]

_LEGACY_SCRIPT = 'legacy_marker = "from the original script"\nprint(legacy_marker)\n'

_WALK_VALIDATE_CODES = [
    "dae.lab.validate.collector_incomplete_group",
    "dae.lab.validate.collector_no_walks",
    "dae.lab.validate.walks_reach_flight_collector",
    "dae.lab.validate.emitter_multi_successor",
    "dae.lab.validate.walk_budget_exceeded",
    "dae.lab.validate.config_walk_budget_exceeded",
    "dae.lab.validate.reserved_separator_in_id",
]


def _visualize_payload() -> dict:
    """The ``data`` payload of ``dae --json lab visualize`` in an empty cwd."""
    runner = CliRunner()
    with _isolated_cwd():
        result = runner.invoke(app, ["--json", "lab", "visualize"], prog_name="dae")
    assert result.exit_code == OK_EXIT
    # the envelope nests the payload under data
    return json.loads(result.stdout)["data"]


def _human_stdout(runner: CliRunner, argv: list[str]) -> str:
    """Text of ``argv`` on the human path, captured at the rich ``out`` Console."""
    from daedalus.cli.console import out

    # `out` is bound to the real stdout at import, so CliRunner's redirect never
    # captures it; out.capture() intercepts at the Console level.
    with out.capture() as captured:
        runner.invoke(app, argv, prog_name="dae")
    return captured.get()


def _write_inline_lab(lab_dir: Path, modules: list[tuple[str, str, list[str]]]) -> Path:
    """Scaffold a lab from (id, role, depends) rows, no main.py; return lab.yaml."""
    lines = [f"name: {lab_dir.name}", "modules:"]
    for mid, role, depends in modules:
        (lab_dir / "modules" / mid).mkdir(parents=True)
        (lab_dir / "modules" / mid / "dae-module.yaml").write_text(f"role: {role}\n")
        lines.append(f"  - id: {mid}")
        if depends:
            lines.append(f"    depends: [{', '.join(depends)}]")
    recipe_path = lab_dir / "lab.yaml"
    recipe_path.write_text("\n".join(lines) + "\n")
    return recipe_path


def _visualize_payload_in(lab_dir: Path) -> dict:
    """The ``data`` payload of ``lab visualize`` with cwd inside ``lab_dir``."""
    runner = CliRunner()
    with chdir(lab_dir):
        result = runner.invoke(app, ["--json", "lab", "visualize"], prog_name="dae")
    assert result.exit_code == OK_EXIT
    # the envelope nests the payload under data
    return json.loads(result.stdout)["data"]
