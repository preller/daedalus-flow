"""Copy and generated-artifact contract of the guided flow.

Copy lives in ``strings.py``; tests read the human stdout and the generated files.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from daedalus.cli import strings
from daedalus.cli.app import app
from tests.cli._cli_contract import (
    _copy_fixture_lab,
    _human_stdout,
    _isolated_cwd,
    _reset_json_state,
    runner,
)

pytestmark = pytest.mark.integration

# Re-export imported fixtures so ruff does not flag them; pytest resolves by name.
__all__ = ["_reset_json_state", "runner"]


# scaffold verb


def test_example_help_calls_the_write_a_scaffold_not_a_preview() -> None:
    """`dae example --help` describes the write as "scaffold", never "preview"."""
    result = CliRunner().invoke(app, ["example", "--help"], prog_name="dae")
    assert result.exit_code == 0, result.output
    text = result.output.lower()
    assert "scaffold" in text, result.output
    assert "preview" not in text, result.output


def test_example_callback_docstring_uses_scaffold_verb() -> None:
    """The example callback help string, where the verb lives, says scaffold."""
    from daedalus.cli.commands.example import example as example_app

    help_text = (example_app.info.help or "").lower()
    assert "scaffold" in help_text, help_text
    assert "preview" not in help_text, help_text


# post-scaffold Next hint


@pytest.mark.parametrize("name", sorted(strings.NEXT_AFTER_SCAFFOLD))
def test_scaffold_next_hint_routes_through_validate_and_visualize(name: str) -> None:
    """The hint chains validate and visualize before a dry run that writes nothing."""
    hint = strings.NEXT_AFTER_SCAFFOLD[name]
    assert "dae lab validate" in hint, hint
    assert "dae lab visualize" in hint, hint
    assert "--dry-run" in hint, hint
    # validate and visualize precede run on the line.
    assert hint.index("validate") < hint.index("run"), hint
    assert hint.index("visualize") < hint.index("run"), hint


def test_scaffold_result_path_reaches_stdout(runner: CliRunner) -> None:
    """The path is on stdout; the teaching chrome and the Next hint stay on stderr."""
    with _isolated_cwd():
        stdout = _human_stdout(runner, ["example", "minimal"])

    assert "minimal" in stdout, stdout
    # The path leaf the scaffold wrote, ./minimal/, must be locatable on stdout.
    assert "minimal/" in stdout or "minimal" in stdout.split("\n")[0], stdout


def test_converted_main_carries_ctx_read_write_snippet(runner: CliRunner) -> None:
    """The generated main.py shows a concrete read and write, not only the names."""
    with _isolated_cwd():
        Path("legacy_fit.py").write_text("x = 1\n")
        runner.invoke(app, ["module", "convert", "legacy_fit.py"], prog_name="dae")
        main_text = Path("modules/legacy_fit/main.py").read_text()

    assert "ctx.step_input_path" in main_text, main_text
    assert "ctx.step_output_path" in main_text, main_text
    # a concrete read and a concrete write are shown, not only the names.
    assert ".open(" in main_text or "read_text(" in main_text or "/ " in main_text, (
        main_text
    )
    assert "write_text(" in main_text or ".open(" in main_text, main_text


def test_convert_output_prints_ctx_snippet(runner: CliRunner) -> None:
    """The convert command output (human stdout) shows the ctx read/write snippet."""
    with _isolated_cwd():
        Path("legacy_fit.py").write_text("x = 1\n")
        out = _human_stdout(runner, ["module", "convert", "legacy_fit.py"])

    assert "ctx.step_input_path" in out, out
    assert "ctx.step_output_path" in out, out


def test_converted_manifest_has_role_comment(runner: CliRunner) -> None:
    """The generated dae-module.yaml carries a role comment, not a bare scalar."""
    with _isolated_cwd():
        Path("legacy_fit.py").write_text("x = 1\n")
        runner.invoke(app, ["module", "convert", "legacy_fit.py"], prog_name="dae")
        manifest = Path("modules/legacy_fit/dae-module.yaml").read_text()

    assert "role: transform" in manifest, manifest
    assert "#" in manifest, manifest  # a comment line is present
    assert "role" in manifest.lower(), manifest


def test_created_manifest_has_role_comment(runner: CliRunner) -> None:
    """`module create` likewise writes a commented role manifest (one pattern)."""
    with _isolated_cwd():
        runner.invoke(app, ["module", "create", "normalize"], prog_name="dae")
        manifest = Path("modules/normalize/dae-module.yaml").read_text()

    assert "role: transform" in manifest, manifest
    assert "#" in manifest, manifest


def test_convert_output_points_at_wrapping_into_a_lab(runner: CliRunner) -> None:
    """The output names lab init as the way to wrap the module into a lab."""
    with _isolated_cwd():
        Path("legacy_fit.py").write_text("x = 1\n")
        out = _human_stdout(runner, ["module", "convert", "legacy_fit.py"])

    assert "lab init" in out, out


def test_module_try_makes_no_execution_promise(runner: CliRunner) -> None:
    """try previews the FlowContext; "smoke test" would read as "it ran my code"."""
    with _isolated_cwd():
        runner.invoke(app, ["module", "create", "normalize"], prog_name="dae")
        out = _human_stdout(runner, ["module", "try", "modules/normalize"]).lower()

    # No false execution promise: "smoke test" reads as "it ran my code".
    assert "smoke test" not in out, out
    assert "ran your code" not in out, out
    # It must affirmatively state nothing runs (preview/inspect, not execute).
    assert "nothing" in out and ("preview" in out or "runs nothing" in out), out


def test_try_intro_string_makes_no_execution_promise() -> None:
    """The try intro copy in strings.py says preview or inspect, not smoke test."""
    intro = strings.try_intro("modules/fit_nested").lower()
    assert "smoke test" not in intro, intro
    assert "preview" in intro or "inspect" in intro, intro


def test_serial_run_footer_signals_serial_and_max_workers(tmp_path: Path) -> None:
    """The human run output notes serial execution and points at max_workers."""
    lab = _copy_fixture_lab("linear_smoke", tmp_path)
    runner = CliRunner()
    from tests._helpers import chdir

    with chdir(lab):
        out = _human_stdout(runner, ["lab", "run"]).lower()

    assert "serial" in out, out
    assert "max_workers" in out, out


def test_serial_run_footer_names_serial_and_the_parallel_path() -> None:
    """The serial-run footer copy in strings.py names serial and the parallel path."""
    note = strings.SERIAL_RUN_NOTE.lower()
    assert "serial" in note, note
    assert "max_workers" in note, note
    assert "prefect" in note, note
