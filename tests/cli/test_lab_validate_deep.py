"""``dae lab validate`` resolves strategies; ``--deep`` also builds and imports.

The nudge is asserted via a ``chrome.note`` spy, since CliRunner misses stderr.
"""

from __future__ import annotations

import json
from typing import cast

import pytest
from typer.testing import CliRunner

from daedalus.cli import chrome
from daedalus.cli.app import app
from tests._helpers import chdir
from tests.cli._cli_contract import _copy_fixture_lab, _reset_json_state

__all__ = ["_reset_json_state"]

OK_EXIT = 0
FAILURE_EXIT = 1

# A stdlib-only entry imports clean under any standalone interpreter, so a deep
# probe of it passes with no network beyond the managed interpreter itself.
_CLEAN_MAIN = """\
import json

import daedalus.flow as dae


@dae.entry
def run(ctx: dae.FlowContext) -> None:
    pass
"""

# An entry whose top-level import names a package that does not exist: the deep
# probe loads main.py, the import raises, and the module fails as load_failed.
_BROKEN_MAIN = """\
import totally_absent_pkg_zzz

import daedalus.flow as dae


@dae.entry
def run(ctx: dae.FlowContext) -> None:
    pass
"""


def _write_uv_lab(lab_dir, module_id: str, main_body: str):
    """Scaffold a one-module ``isolation: uv`` lab; plain validate passes on it."""
    module_dir = lab_dir / "modules" / module_id
    module_dir.mkdir(parents=True)
    (module_dir / "dae-module.yaml").write_text("role: transform\n")
    (module_dir / "main.py").write_text(main_body)
    lines = [
        f"name: {lab_dir.name}",
        "isolation: uv",
        "modules:",
        f"  - id: {module_id}",
    ]
    (lab_dir / "lab.yaml").write_text("\n".join(lines) + "\n")
    return lab_dir


def _validate_envelope(lab_dir, *args: str) -> tuple[int, dict]:
    """Run ``dae --json lab validate <args>`` in ``lab_dir``; return exit + envelope."""
    runner = CliRunner()
    with chdir(lab_dir):
        result = runner.invoke(
            app, ["--json", "lab", "validate", *args], prog_name="dae"
        )
    return result.exit_code, json.loads(result.stdout)


# --- plain validate nudges (fast, never builds) ----------------------------


def test_validate_deep_nudge_string_phrasing() -> None:
    """The nudge names the count, pluralizes, and points at ``validate --deep``."""
    from daedalus.cli import strings

    one = strings.validate_deep_nudge(1)
    many = strings.validate_deep_nudge(3)
    assert "1 module needs" in one
    assert "3 modules need" in many
    for text in (one, many):
        assert "closure builds" in text
        assert "dae lab validate --deep" in text


def test_plain_validate_nudges_toward_deep_and_never_builds(
    tmp_path, monkeypatch
) -> None:
    """With a nix module, plain validate is ok, nudges to --deep, builds nothing."""
    import daedalus.core.engine.isolation as iso

    lab = _copy_fixture_lab("science_nix", tmp_path)
    notes: list[str] = []
    builds: list[object] = []
    monkeypatch.setattr(chrome, "note", notes.append)
    monkeypatch.setattr(iso, "_nix_build", lambda *a, **k: builds.append((a, k)))

    runner = CliRunner()
    with chdir(lab):
        result = runner.invoke(app, ["lab", "validate"], prog_name="dae")

    assert result.exit_code == OK_EXIT, result.output
    assert any("closure builds" in n and "validate --deep" in n for n in notes), notes
    assert builds == []  # plain validate resolves only; it never provisions/builds


def test_plain_validate_does_not_nudge_when_all_ambient(tmp_path, monkeypatch) -> None:
    """An isolation-unset K=1 lab resolves all-ambient, so there is no --deep nudge."""
    lab = _copy_fixture_lab("chain_plain", tmp_path)
    notes: list[str] = []
    monkeypatch.setattr(chrome, "note", notes.append)

    runner = CliRunner()
    with chdir(lab):
        result = runner.invoke(app, ["lab", "validate"], prog_name="dae")

    assert result.exit_code == OK_EXIT, result.output
    assert not any("validate --deep" in n for n in notes), notes


# --- --deep catches an unimportable module (real uv probe) -----------------


@pytest.mark.integration
def test_deep_on_a_clean_uv_lab_is_ok(tmp_path) -> None:
    """A stdlib-only uv module imports clean under the standalone interpreter."""
    lab = _write_uv_lab(tmp_path / "clean", "reduce", _CLEAN_MAIN)
    exit_code, envelope = _validate_envelope(lab, "--deep")
    assert exit_code == OK_EXIT, envelope
    assert envelope["code"] == "dae.lab.validate.ok"
    assert envelope["error"] is None


@pytest.mark.integration
def test_deep_fails_load_failed_on_an_unimportable_module(tmp_path) -> None:
    """--deep imports each entry; a missing top-level package is load_failed."""
    lab = _write_uv_lab(tmp_path / "broken", "reduce", _BROKEN_MAIN)
    exit_code, envelope = _validate_envelope(lab, "--deep")

    assert exit_code == FAILURE_EXIT, envelope
    # The verdict stays a validate code; the per-module cause rides the error slot.
    assert envelope["code"] == "dae.lab.validate.isolation_unbacked"
    assert envelope["error"]["code"] == "dae.step.load_failed"
    assert envelope["error"]["module"] == "reduce"
    # No science, no lineage: a deep failure is caught before anything is written.
    assert not (lab / "dae-outputs").exists()
    assert not (lab / "flows").exists()


def test_deep_failure_resolution_helper_shapes_the_cause(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The envelope shape is pinned without paying the real probe cost."""
    from daedalus.cli.commands._outcome import state
    from daedalus.cli.commands.lab import _resolve_deep_failure

    captured: dict[str, object] = {}

    def _capture(outcome, payload=None, *, error=None) -> None:
        captured["code"] = str(outcome)
        captured["exit"] = outcome.exit_code
        captured["error"] = error

    import daedalus.cli.commands.lab as lab_cmd

    monkeypatch.setattr(lab_cmd, "resolve", _capture)
    state["json"] = True
    try:
        _resolve_deep_failure("preprocess", "closure built but numpy will not import")
    finally:
        state["json"] = False

    assert captured["code"] == "dae.lab.validate.isolation_unbacked"
    assert captured["exit"] == FAILURE_EXIT
    error = cast("dict[str, str]", captured["error"])
    assert error["code"] == "dae.step.load_failed"
    assert error["module"] == "preprocess"
    assert "numpy will not import" in error["reason"]


# --- distinguish an unbuildable closure from an unimportable module --------


def test_deep_separates_a_build_failure_from_an_import_failure(
    tmp_path, monkeypatch
) -> None:
    """A build failure carries the nix log pointer; an import failure does not."""
    from daedalus.cli.commands.lab import _validate
    from daedalus.core import recipe
    from daedalus.core.engine import isolation as iso
    from daedalus.core.engine import subprocess_runner as sr

    lab = _copy_fixture_lab("science_nix", tmp_path)
    spec = recipe.load_recipe(lab / "lab.yaml")
    pairs = _validate._lab_resolution_pairs(spec, lab)

    def _build_fails(self, module_dir, *, log_dir=None) -> None:
        raise iso.NixProvisionError(
            "nix build failed for /flake (rc=1): builder failed\n"
            "full nix log: /flake/nix-build.log"
        )

    monkeypatch.setattr(iso.NixStrategy, "provision", _build_fails)
    build_failure = _validate.deep_validate(lab, pairs)
    assert build_failure is not None
    build_module, build_cause = build_failure
    assert build_module == "solve"
    assert "nix build failed" in build_cause
    assert "nix-build.log" in build_cause

    def _builds(self, module_dir, *, log_dir=None) -> None:
        return None

    def _import_fails(module_dir, *, strategy_name, flake_ref=None, **_kwargs):
        return sr.SubprocessStepResult(
            status="failed",
            returncode=1,
            missing_package=None,
            error=(
                "failed to load step from /flake/main.py: "
                "libopenblas.so.0: cannot open shared object file"
            ),
            stderr="",
        )

    monkeypatch.setattr(iso.NixStrategy, "provision", _builds)
    monkeypatch.setattr(sr, "probe_import", _import_fails)
    import_failure = _validate.deep_validate(lab, pairs)
    assert import_failure is not None
    _import_module, import_cause = import_failure
    assert "failed to load step" in import_cause
    # The import cause carries no build-log pointer, so the two causes stay apart.
    assert "nix build failed" not in import_cause
    assert "nix-build.log" not in import_cause
