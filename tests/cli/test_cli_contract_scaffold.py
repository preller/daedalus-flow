"""CLI contract tests for the scaffold verbs: init, module, example and clean.

Helpers, constants and fixtures live in ``tests.cli._cli_contract``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from daedalus.cli.app import app
from tests.cli._cli_contract import (
    _LEGACY_SCRIPT,
    OK_EXIT,
    USAGE_EXIT,
    _human_stdout,
    _isolated_cwd,
    _json_code,
    _reset_json_state,
    run_cli,
    runner,
)

pytestmark = pytest.mark.integration  # integration tier, CLI command chains

# Re-export imported fixtures so flake8/ruff do not flag them as unused; pytest
# resolves them by name in this module's namespace.
__all__ = ["_reset_json_state", "runner"]


@pytest.mark.parametrize(
    ("argv", "ok_code", "exists_code"),
    [
        (["--json", "lab", "init", "x"], "dae.lab.init.ok", "dae.lab.init.exists"),
        (
            ["--json", "module", "create", "foo"],
            "dae.module.create.ok",
            "dae.module.create.exists",
        ),
        (
            ["--json", "example", "minimal"],
            "dae.example.scaffold.ok",
            "dae.example.scaffold.exists",
        ),
    ],
    ids=["lab_init", "module_create", "example_minimal"],
)
def test_scaffold_twice_collides(
    runner: CliRunner, argv: list[str], ok_code: str, exists_code: str
) -> None:
    """Both invocations share one cwd, so the second refuses to clobber the first."""
    with _isolated_cwd():
        first = runner.invoke(app, argv, prog_name="dae")
        second = runner.invoke(app, argv, prog_name="dae")

    assert (first.exit_code, _json_code(first)) == (OK_EXIT, ok_code)
    assert (second.exit_code, _json_code(second)) == (USAGE_EXIT, exists_code)


def test_module_convert_writes_a_real_module(runner: CliRunner) -> None:
    """main.py wraps the script body in a @dae.entry function named for the stem."""
    with _isolated_cwd():
        Path("legacy_fit.py").write_text(_LEGACY_SCRIPT)
        result = runner.invoke(
            app, ["--json", "module", "convert", "legacy_fit.py"], prog_name="dae"
        )
        # Capture filesystem state inside the block; _isolated_cwd restores cwd
        # on exit.
        main_py = Path("modules/legacy_fit/main.py")
        manifest = Path("modules/legacy_fit/dae-module.yaml")
        wrote_main, wrote_manifest = main_py.is_file(), manifest.is_file()
        main_text = main_py.read_text() if wrote_main else ""

    assert (result.exit_code, _json_code(result)) == (OK_EXIT, "dae.module.convert.ok")
    assert wrote_main and wrote_manifest
    assert "@dae.entry" in main_text
    assert "def legacy_fit(ctx: dae.FlowContext)" in main_text
    assert "legacy_marker" in main_text  # the script body was pasted in
    assert "ctx.step_input_path" in main_text  # the ctx-wiring guidance comment


def test_module_convert_twice_collides(runner: CliRunner) -> None:
    """A second convert into an existing module refuses to clobber (exit 2)."""
    with _isolated_cwd():
        Path("legacy_fit.py").write_text(_LEGACY_SCRIPT)
        first = runner.invoke(
            app, ["--json", "module", "convert", "legacy_fit.py"], prog_name="dae"
        )
        second = runner.invoke(
            app, ["--json", "module", "convert", "legacy_fit.py"], prog_name="dae"
        )

    assert (first.exit_code, _json_code(first)) == (OK_EXIT, "dae.module.convert.ok")
    assert (second.exit_code, _json_code(second)) == (
        USAGE_EXIT,
        "dae.module.convert.exists",
    )


def test_module_convert_dry_run_writes_nothing(runner: CliRunner) -> None:
    """`--dry-run` previews (PREVIEW_ONLY) and writes no module directory."""
    from daedalus.cli.strings import PREVIEW_ONLY

    with _isolated_cwd():
        Path("legacy_fit.py").write_text(_LEGACY_SCRIPT)
        preview = _human_stdout(
            runner, ["module", "convert", "legacy_fit.py", "--dry-run"]
        )
        result = runner.invoke(
            app,
            ["--json", "module", "convert", "legacy_fit.py", "--dry-run"],
            prog_name="dae",
        )
        wrote_dir = Path("modules/legacy_fit").exists()

    assert (result.exit_code, _json_code(result)) == (
        OK_EXIT,
        "dae.module.convert.dry_run",
    )
    assert not wrote_dir
    assert PREVIEW_ONLY in preview


def test_module_convert_generated_module_validates(runner: CliRunner) -> None:
    """convert then `module validate <id>` passes: the generated module is sound."""
    with _isolated_cwd():
        Path("legacy_fit.py").write_text(_LEGACY_SCRIPT)
        runner.invoke(app, ["module", "convert", "legacy_fit.py"], prog_name="dae")
        validated = runner.invoke(
            app, ["--json", "module", "validate", "legacy_fit"], prog_name="dae"
        )

    assert (validated.exit_code, _json_code(validated)) == (
        OK_EXIT,
        "dae.module.validate.ok",
    )


def test_module_convert_real_write_banner_is_not_a_preview(runner: CliRunner) -> None:
    """The real-write convert banner names the conversion; it is not a preview."""
    from daedalus.cli.strings import PREVIEW_ONLY

    with _isolated_cwd():
        Path("legacy_fit.py").write_text(_LEGACY_SCRIPT)
        written = _human_stdout(runner, ["module", "convert", "legacy_fit.py"])

    assert PREVIEW_ONLY not in written
    assert "convert" in written.lower()


def test_module_validate_resolves_bare_id_under_modules(runner: CliRunner) -> None:
    """A bare id resolves under modules/, so create then validate needs no path."""
    with _isolated_cwd():
        runner.invoke(app, ["module", "create", "normalize"], prog_name="dae")
        bare = runner.invoke(
            app, ["--json", "module", "validate", "normalize"], prog_name="dae"
        )

    assert (bare.exit_code, _json_code(bare)) == (OK_EXIT, "dae.module.validate.ok")


def test_module_validate_markers_row_reports_the_planted_stub(
    runner: CliRunner,
) -> None:
    """A fresh stub reads 1 unresolved; a replaced raise reads none unresolved."""
    with _isolated_cwd():
        runner.invoke(app, ["module", "create", "widget"], prog_name="dae")
        stubbed = _human_stdout(runner, ["module", "validate", "widget"])

        main_py = Path("modules/widget/main.py")
        resolved_body = (
            '"""widget - resolved."""\n'
            "\n"
            "import daedalus.flow as dae\n"
            "\n"
            "\n"
            "@dae.entry\n"
            "def widget(ctx: dae.FlowContext) -> None:\n"
            "    pass\n"
        )
        main_py.write_text(resolved_body)
        resolved = _human_stdout(runner, ["module", "validate", "widget"])

    assert "1 unresolved (NotImplementedError)" in stubbed, stubbed
    assert "none unresolved" not in stubbed, stubbed
    assert "none unresolved" in resolved, resolved


def test_lab_clean_removes_roots_and_spares_others(runner: CliRunner) -> None:
    """`lab clean` removes the two roots and leaves unrelated files untouched."""
    with _isolated_cwd():
        # the two clean roots plus an unrelated file beside them
        os.mkdir(".daedalus")
        os.makedirs("dae-outputs/flows")
        with open("keep.txt", "w") as handle:
            handle.write("keep me")

        result = runner.invoke(app, ["--json", "lab", "clean"], prog_name="dae")

        # assert (inside the cwd, before it is restored)
        roots_gone = not os.path.exists(".daedalus") and not os.path.exists(
            "dae-outputs"
        )
        unrelated_survived = os.path.exists("keep.txt")

    assert (result.exit_code, _json_code(result)) == (OK_EXIT, "dae.lab.clean.ok")
    assert roots_gone
    assert unrelated_survived
    # The uniform envelope puts paths under `paths` (the same key init / create /
    # convert / scaffold use), never the divergent `removed`.
    data = json.loads(result.stdout)["data"]
    assert "removed" not in data, data
    assert sorted(Path(p).name for p in data["paths"]) == [".daedalus", "dae-outputs"]


def test_lab_clean_nothing_when_empty(runner: CliRunner) -> None:
    """`lab clean` in a cwd with no roots is a no-op success (clean.nothing)."""
    with _isolated_cwd():
        result = runner.invoke(app, ["--json", "lab", "clean"], prog_name="dae")

    assert (result.exit_code, _json_code(result)) == (OK_EXIT, "dae.lab.clean.nothing")


@pytest.mark.parametrize(
    "argv",
    [
        ("lab", "init", "/tmp/dae_escape_abs"),  # noqa: S108 (escape-test vector)
        ("lab", "init", "../dae_escape_dotdot"),
        ("module", "create", "/tmp/dae_escape_mod_abs"),  # noqa: S108 (escape vector)
        ("module", "create", "../../dae_escape_mod_dotdot"),
    ],
)
def test_scaffold_refuses_to_escape_cwd(argv: tuple[str, ...]) -> None:
    """An absolute or cwd-escaping name is refused (exit 2) before any write."""
    exit_code, code = run_cli(*argv)
    assert exit_code == USAGE_EXIT
    assert code is None  # a Typer usage error emits no JSON outcome object


@pytest.mark.parametrize(
    ("write_argv", "preview_argv"),
    [
        (["lab", "init", "demo"], ["lab", "init", "other", "--dry-run"]),
        (["module", "create", "foo"], ["module", "create", "bar", "--dry-run"]),
    ],
    ids=["lab_init", "module_create"],
)
def test_scaffold_real_write_banner_says_created_not_preview(
    runner: CliRunner, write_argv: list[str], preview_argv: list[str]
) -> None:
    """The real-write banner says created; the --dry-run twin previews."""
    from daedalus.cli.strings import PREVIEW_ONLY

    with _isolated_cwd():
        written = _human_stdout(runner, write_argv)
        preview = _human_stdout(runner, preview_argv)

    assert PREVIEW_ONLY not in written
    assert "created" in written.lower()
    assert PREVIEW_ONLY in preview
