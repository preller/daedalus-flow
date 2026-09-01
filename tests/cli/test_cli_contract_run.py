"""CLI contract tests for ``lab run``: exit code, ``--json`` code and lineage.

Helpers, constants and fixtures live in ``tests.cli._cli_contract``.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from daedalus.cli.app import app
from tests._helpers import chdir
from tests.cli._cli_contract import (
    _BROKEN_LABS,
    FAILURE_EXIT,
    OK_EXIT,
    USAGE_EXIT,
    _copy_fixture_lab,
    _flows_dir,
    _only_flow,
    _reset_json_state,
    _run_cli_in,
    _write_inline_lab,
    run_cli,
)

pytestmark = pytest.mark.integration  # integration tier, CLI command chains

# Re-export imported fixtures so flake8/ruff do not flag them as unused; pytest
# resolves them by name in this module's namespace.
__all__ = ["_reset_json_state"]


def test_lab_run_not_found_in_empty_cwd() -> None:
    """`lab run` in a directory with no lab.yaml is a usage not_found (exit 2)."""
    assert run_cli("lab", "run") == (USAGE_EXIT, "dae.lab.run.not_found")


def test_lab_run_invalid_on_unparseable_lab(tmp_path: Path) -> None:
    """An unparseable lab.yaml refuses as invalid (exit 2) and writes no lineage."""
    shutil.copyfile(_BROKEN_LABS / "unparseable.yaml", tmp_path / "lab.yaml")
    assert _run_cli_in(tmp_path, "lab", "run") == (USAGE_EXIT, "dae.lab.run.invalid")
    assert not _flows_dir(tmp_path).exists()


def test_lab_run_invalid_on_missing_module_manifest(tmp_path: Path) -> None:
    """A module dir without dae-module.yaml is refused before the run starts."""
    lab = _copy_fixture_lab("linear_smoke", tmp_path)
    (lab / "modules" / "debug_io" / "dae-module.yaml").unlink()
    assert _run_cli_in(lab, "lab", "run") == (USAGE_EXIT, "dae.lab.run.invalid")
    assert not _flows_dir(lab).exists()


def test_lab_run_invalid_on_out_of_set_role(tmp_path: Path) -> None:
    """A role outside the Role set is refused before the run starts (exit 2)."""
    lab = _copy_fixture_lab("linear_smoke", tmp_path)
    (lab / "modules" / "debug_io" / "dae-module.yaml").write_text("role: banana\n")
    assert _run_cli_in(lab, "lab", "run") == (USAGE_EXIT, "dae.lab.run.invalid")
    assert not _flows_dir(lab).exists()


def test_lab_run_diamond_join_runs_end_to_end(tmp_path: Path) -> None:
    """diamond_join, a branching DAG, runs to completion at M=1 (exit 0)."""
    lab = _copy_fixture_lab("diamond_join", tmp_path)
    assert _run_cli_in(lab, "lab", "run") == (OK_EXIT, "dae.lab.run.ok")

    flow = _only_flow(lab)
    # run-once manifests live in .daedalus/ (config copies carry none); diamond_join
    # is branched, so the flow record auto-bumps to format_version 3 (user_walk).
    manifests = sorted((lab / ".daedalus").rglob("dae-manifest.json"))
    assert len(manifests) == 4, f"expected 4 step manifests, found {manifests}"
    for manifest_path in manifests:
        manifest = json.loads(manifest_path.read_text())
        assert manifest["status"] == "completed"
    # The .daedalus/ store holds the manifests; the per-config copies under the
    # flow tree hold none. Globbing only .daedalus would miss a regression that
    # also wrote manifests into the copies.
    assert sorted(flow.rglob("dae-manifest.json")) == []
    flow_record = json.loads((flow / "dae-flow.json").read_text())
    # user_walk (v3) plus per-step timing (v4) put this record at the v4 floor.
    # The floor rather than a literal lets a later additive bump pass.
    assert flow_record["format_version"] >= 4
    assert flow_record["status"] == "completed"


def test_lab_run_broadcast_shape_stays_unsupported(tmp_path: Path) -> None:
    """A multi-parent broadcast shape refuses as unsupported before any execution."""
    lab_dir = tmp_path / "broadcast"
    _write_inline_lab(
        lab_dir,
        [
            ("seed", "transform", []),
            ("p", "transform", ["seed"]),
            ("q", "transform", ["seed"]),
            ("j1", "walk_collector", ["p", "q"]),
            ("mid", "transform", ["j1"]),
            ("m", "transform", ["mid"]),
            ("n", "transform", ["mid"]),
            ("tt", "transform", ["j1", "m"]),
        ],
    )
    assert _run_cli_in(lab_dir, "lab", "run") == (
        USAGE_EXIT,
        "dae.lab.run.unsupported",
    )
    assert not _flows_dir(lab_dir).exists()
    # The stderr note must name the broadcast shape, not the retired "tiny engine
    # runs only linear labs" message, which exits 2 with the same code.
    from daedalus.cli.console import err

    with chdir(lab_dir), err.capture() as captured:
        CliRunner().invoke(app, ["lab", "run"], prog_name="dae")
    note = captured.get()
    assert "linear labs" not in note
    assert "broadcast" in note


def test_lab_run_invalid_on_emitter_fanout(tmp_path: Path) -> None:
    """An emitter with two successors is invalid (exit 2), not unsupported."""
    lab_dir = tmp_path / "emitter_fanout"
    _write_inline_lab(
        lab_dir,
        [
            ("src", "emitter", []),
            ("a", "transform", ["src"]),
            ("b", "transform", ["src"]),
        ],
    )
    assert _run_cli_in(lab_dir, "lab", "run") == (USAGE_EXIT, "dae.lab.run.invalid")
    assert not _flows_dir(lab_dir).exists()


def test_lab_run_dry_run_on_diamond_join_writes_nothing(tmp_path: Path) -> None:
    """diamond_join reaches the dry-run preview instead of the unsupported refusal."""
    lab = _copy_fixture_lab("diamond_join", tmp_path)
    assert _run_cli_in(lab, "lab", "run", "--dry-run") == (
        OK_EXIT,
        "dae.lab.run.dry_run",
    )
    assert not (lab / "dae-outputs").exists()


def test_lab_run_ok_writes_lineage(tmp_path: Path) -> None:
    """linear_smoke runs (exit 0) and every manifest reads completed."""
    lab = _copy_fixture_lab("linear_smoke", tmp_path)
    assert _run_cli_in(lab, "lab", "run") == (OK_EXIT, "dae.lab.run.ok")

    flow = _only_flow(lab)
    # The five run-once instances land in .daedalus/ with version-2 manifests;
    # the flow record is v4 because FlowStep carries per-step timing.
    manifests = sorted((lab / ".daedalus").rglob("dae-manifest.json"))
    assert len(manifests) == 5, f"expected 5 step manifests, found {manifests}"
    for manifest_path in manifests:
        manifest = json.loads(manifest_path.read_text())
        assert manifest["status"] == "completed"
        # The walk identity fields (flight_id, walk_id) put these manifests at v2;
        # the floor rather than a literal lets a later additive bump pass.
        assert manifest["format_version"] >= 2
    flow_record = json.loads((flow / "dae-flow.json").read_text())
    assert flow_record["format_version"] >= 4
    assert flow_record["status"] == "completed"
    assert flow_record["lab_name"] == "linear_smoke"
    assert (flow / "final" / "run_report.json").exists()


def test_lab_run_ok_writes_final_dir(tmp_path: Path) -> None:
    """final/ holds the sink files and no dae-manifest.json; the old output/ is gone."""
    lab = _copy_fixture_lab("linear_smoke", tmp_path)
    assert _run_cli_in(lab, "lab", "run") == (OK_EXIT, "dae.lab.run.ok")

    flow = _only_flow(lab)
    out = flow / "final"
    assert (out / "run_report.json").exists()
    assert not (out / "dae-manifest.json").exists()
    assert not (flow / "output").exists()


def test_lab_run_dry_run_writes_nothing(tmp_path: Path) -> None:
    """A dry run over linear_smoke previews and leaves no dae-outputs root behind."""
    lab = _copy_fixture_lab("linear_smoke", tmp_path)
    assert _run_cli_in(lab, "lab", "run", "--dry-run") == (
        OK_EXIT,
        "dae.lab.run.dry_run",
    )
    # The whole dae-outputs root must be absent, not only flows/, so an empty
    # dae-outputs/ shell left by a dry run is caught too.
    assert not (lab / "dae-outputs").exists()


def test_lab_run_failed_records_failure(tmp_path: Path) -> None:
    """A raising step gives exit 1, a failed manifest and a failed flow record."""
    lab = _copy_fixture_lab("linear_smoke", tmp_path)
    boom_dir = lab / "modules" / "boom"
    boom_dir.mkdir()
    (boom_dir / "dae-module.yaml").write_text("role: transform\n")
    (boom_dir / "main.py").write_text(
        "import daedalus.flow as dae\n\n\n"
        "@dae.entry\n"
        "def boom(ctx: dae.FlowContext) -> None:\n"
        '    raise RuntimeError("boom raised for the test")\n'
    )
    lab_yaml = (lab / "lab.yaml").read_text()
    lab_yaml += "\n  - id: boom\n    depends: [collect_report]\n"
    (lab / "lab.yaml").write_text(lab_yaml)

    assert _run_cli_in(lab, "lab", "run") == (FAILURE_EXIT, "dae.lab.run.failed")

    flow = _only_flow(lab)
    # Run-once dirs live in .daedalus/.
    boom_manifests = list((lab / ".daedalus").rglob("*_boom/dae-manifest.json"))
    assert len(boom_manifests) == 1, (
        f"expected one boom manifest, found {boom_manifests}"
    )
    assert json.loads(boom_manifests[0].read_text())["status"] == "failed"
    flow_record = json.loads((flow / "dae-flow.json").read_text())
    assert flow_record["status"] == "failed"
    # a failed flow writes no per-flow final/ copy (completion-only)
    assert not (flow / "final").exists()
    assert not (flow / "output").exists()


def test_lab_run_missing_deps_clean_outcome(tmp_path: Path) -> None:
    """An absent third-party package gives missing_deps (exit 1), not failed."""
    lab = _copy_fixture_lab("linear_smoke", tmp_path)
    mod_dir = lab / "modules" / "needs_absent_pkg"
    mod_dir.mkdir()
    (mod_dir / "dae-module.yaml").write_text("role: transform\n")
    (mod_dir / "main.py").write_text(
        "import no_such_pkg_dae_test\n\n"
        "import daedalus.flow as dae\n\n\n"
        "@dae.entry\n"
        "def needs_absent_pkg(ctx: dae.FlowContext) -> None:\n"
        "    pass\n"
    )
    lab_yaml = (lab / "lab.yaml").read_text()
    lab_yaml += "\n  - id: needs_absent_pkg\n    depends: [collect_report]\n"
    (lab / "lab.yaml").write_text(lab_yaml)

    assert _run_cli_in(lab, "lab", "run") == (
        FAILURE_EXIT,
        "dae.lab.run.missing_deps",
    )

    flow = _only_flow(lab)
    # Run-once dirs live in .daedalus/.
    manifests = list((lab / ".daedalus").rglob("*_needs_absent_pkg/dae-manifest.json"))
    assert len(manifests) == 1, f"expected one manifest, found {manifests}"
    manifest = json.loads(manifests[0].read_text())
    assert manifest["status"] == "failed"
    assert "missing_deps:" not in (manifest.get("error") or ""), (
        "internal signal tag leaked into the persisted lineage manifest"
    )
    # a missing-deps failure writes no per-flow final/ copy (completion-only)
    assert not (flow / "final").exists()
    assert not (flow / "output").exists()


def test_missing_deps_hint_points_at_real_provisioning_not_a_future_feature() -> None:
    """Isolation is switched on by ``max_workers > 1`` in lab.yaml; the hint says so."""
    from daedalus.cli.strings import MISSING_DEPS_HINT

    assert "max_workers" in MISSING_DEPS_HINT, MISSING_DEPS_HINT
    assert "future feature" not in MISSING_DEPS_HINT, MISSING_DEPS_HINT


def test_lab_run_engine_unavailable_when_prefect_extra_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``engine: prefect`` without the extra refuses at engine selection (exit 1)."""
    from daedalus.cli.commands import lab as lab_cmd

    monkeypatch.setattr(lab_cmd, "_prefect_available", lambda: False)

    lab = _copy_fixture_lab("linear_smoke", tmp_path)
    lab_yaml = (lab / "lab.yaml").read_text()
    (lab / "lab.yaml").write_text("engine: prefect\n" + lab_yaml)

    assert _run_cli_in(lab, "lab", "run") == (
        FAILURE_EXIT,
        "dae.lab.run.engine_unavailable",
    )
    # No flow lineage and no run-once store: the refusal comes before any write.
    flows = lab / "dae-outputs" / "flows"
    assert not flows.exists() or not any(flows.iterdir()), (
        "engine_unavailable must refuse before the engine writes a flow"
    )
    assert not (lab / ".daedalus").exists(), (
        "engine_unavailable must refuse before any run-once store is created"
    )


def test_engine_unavailable_hint_names_the_extra_install() -> None:
    from daedalus.cli.strings import ENGINE_UNAVAILABLE_HINT

    assert "daedalus-flow[engine]" in ENGINE_UNAVAILABLE_HINT, ENGINE_UNAVAILABLE_HINT
    assert "pip install" in ENGINE_UNAVAILABLE_HINT, ENGINE_UNAVAILABLE_HINT


def test_lab_run_installed_pkg_broken_submodule_stays_failed(tmp_path: Path) -> None:
    """json imports, so a missing submodule is a code bug, not a missing dependency."""
    lab = _copy_fixture_lab("linear_smoke", tmp_path)
    mod_dir = lab / "modules" / "broken_import"
    mod_dir.mkdir()
    (mod_dir / "dae-module.yaml").write_text("role: transform\n")
    (mod_dir / "main.py").write_text(
        "import json.no_such_submodule_dae_test\n\n"
        "import daedalus.flow as dae\n\n\n"
        "@dae.entry\n"
        "def broken_import(ctx: dae.FlowContext) -> None:\n"
        "    pass\n"
    )
    lab_yaml = (lab / "lab.yaml").read_text()
    lab_yaml += "\n  - id: broken_import\n    depends: [collect_report]\n"
    (lab / "lab.yaml").write_text(lab_yaml)

    assert _run_cli_in(lab, "lab", "run") == (FAILURE_EXIT, "dae.lab.run.failed")


def test_lab_run_threads_lab_yaml_max_workers_into_the_engine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The engine config carries the lab.yaml value; execution is forced back to K=1."""
    from dataclasses import replace

    from daedalus.core.engine import LabConfig, LocalEngine

    captured: dict[str, int] = {}
    real_execute = LocalEngine.execute_dag

    def _capture(self: LocalEngine, plan: object, config: LabConfig) -> object:
        captured["max_workers"] = config.max_workers
        return real_execute(self, plan, replace(config, max_workers=1))

    monkeypatch.setattr(LocalEngine, "execute_dag", _capture)

    lab = _copy_fixture_lab("linear_smoke", tmp_path)
    text = (lab / "lab.yaml").read_text()
    (lab / "lab.yaml").write_text(text + "\nmax_workers: 3\n")

    exit_code, code = _run_cli_in(lab, "lab", "run")

    assert (exit_code, code) == (OK_EXIT, "dae.lab.run.ok")
    assert captured["max_workers"] == 3
