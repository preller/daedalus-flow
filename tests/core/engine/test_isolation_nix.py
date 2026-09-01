"""Nix isolation tests, from sibling env separation to the refusal when nix is absent.

nix_diamond runs once per module; tests that build skip on a host that cannot.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from daedalus.cli.app import app
from daedalus.core.engine.isolation import NixProvisionError, NixStrategy
from daedalus.core.engine.subprocess_runner import _build_nix_command
from daedalus.core.outcomes import Outcome
from tests._helpers import _copy_lab
from tests.conftest import nix_can_build

_DAE = Path(sys.executable).parent / "dae"

# The module gate skips when `nix eval` fails. A host may pass that and still not
# build uv2nix flakes, so tests that build also go through nix_can_build(). The
# pure-logic guards stay live on such a host.
_NIX_AVAILABLE = NixStrategy().available()
pytestmark = [
    pytest.mark.skipif(
        not _NIX_AVAILABLE,
        reason="nix is unavailable on this host (NixStrategy.available() is False)",
    ),
    pytest.mark.integration,
]


def _run_nix_diamond(lab: Path, *, isolation: str | None = None):
    """Run the copied nix_diamond under LocalEngine; isolation overrides lab.yaml."""
    from daedalus.core.engine import LabConfig, LocalEngine
    from daedalus.core.recipe import build_plan, load_recipe

    spec = load_recipe(lab / "lab.yaml")
    plan = build_plan(spec, lab)
    config = LabConfig(
        lab_name="nix_diamond",
        lab_dir=lab,
        seed=0,
        output_root=lab / "dae-outputs",
        max_workers=spec.max_workers,
        isolation=isolation if isolation is not None else spec.isolation,
    )
    result = LocalEngine().execute_dag(plan, config=config)
    return result, lab


def _lineage_shape(lab: Path) -> dict[str, tuple[str, str]]:
    """(step_id, status) per manifest, keyed by store path; bytes and times ignored."""
    shape: dict[str, tuple[str, str]] = {}
    store = lab / ".daedalus"
    for manifest in sorted(store.glob("**/dae-manifest.json")):
        data = json.loads(manifest.read_text())
        rel = manifest.parent.relative_to(store).as_posix()
        shape[rel] = (data["step_id"], data["status"])
    return shape


def _branch_reports(lab: Path) -> dict[str, dict]:
    """Collect each branch's report.json from the run's .daedalus store."""
    reports: dict[str, dict] = {}
    for report_path in lab.glob(".daedalus/**/report.json"):
        data = json.loads(report_path.read_text())
        reports[data["branch"]] = data
    return reports


@pytest.fixture(scope="module")
def diamond_run(tmp_path_factory: pytest.TempPathFactory):
    """Run the nix diamond once per module; skips where uv2nix flakes cannot build."""
    # a module-scoped fixture cannot use the function-scoped require_nix_build
    if not nix_can_build():
        pytest.skip(
            "this host cannot build uv2nix nix flakes (nix_can_build() is False)"
        )
    lab = _copy_lab("nix_diamond", tmp_path_factory.mktemp("nixdiamond"))
    result, lab = _run_nix_diamond(lab)
    return result, lab, _branch_reports(lab)


def test_positive_isolation_each_sibling_sees_only_its_lib(diamond_run) -> None:
    result, _lab, reports = diamond_run
    assert result.status == "completed", result.error
    assert set(reports) == {"fig", "art"}
    # Each sibling imports its own lib
    assert reports["fig"]["my_lib"] == "pyfiglet"
    assert reports["art"]["my_lib"] == "art"
    # and cannot see the sibling's lib.
    assert reports["fig"]["can_import_art"] is False
    assert reports["art"]["can_import_pyfiglet"] is False


def test_negative_leak_guard_host_only_package_absent(diamond_run) -> None:
    # networkx is a daedalus runtime dep, importable in the dev env, but is in
    # neither module's uv.lock; a host site-packages leak would make it importable.
    import importlib.util

    assert importlib.util.find_spec("networkx") is not None, (
        "networkx must be importable in the dev env for this guard to mean anything"
    )
    _result, _lab, reports = diamond_run
    assert reports["fig"]["can_import_networkx"] is False
    assert reports["art"]["can_import_networkx"] is False


def test_no_silent_fallback_when_nix_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # With nix unavailable the run refuses with isolation_unavailable and writes
    # no flow; it does not fall back to uv or ambient.
    monkeypatch.setattr(NixStrategy, "available", lambda self: False)
    lab = _copy_lab("nix_diamond", tmp_path)
    monkeypatch.chdir(lab)

    result = CliRunner().invoke(app, ["--json", "lab", "run"], prog_name="dae")
    payload = json.loads(result.stdout)

    assert result.exit_code == 1
    assert payload["code"] == Outcome.DAE_LAB_RUN_ISOLATION_UNAVAILABLE.value
    # Refused before any write, so no flow lineage exists.
    assert not (lab / "dae-outputs" / "flows").exists()


def test_isolation_unavailable_outcome_is_a_failure() -> None:
    from daedalus.core.outcomes import Category

    outcome = Outcome.DAE_LAB_RUN_ISOLATION_UNAVAILABLE
    assert outcome.value == "dae.lab.run.isolation_unavailable"
    assert outcome.category is Category.FAILURE


def test_strategy_engaged_marker_in_reports(diamond_run) -> None:
    # Only the nix path sets `DAE_ISOLATION=nix` in the child env.
    _result, _lab, reports = diamond_run
    assert reports["fig"]["isolation_marker"] == "nix"
    assert reports["art"]["isolation_marker"] == "nix"


def test_build_nix_command_is_a_nix_shell_line(tmp_path: Path) -> None:
    # The launch line is a `nix shell <flakeref>#<env> --command python <shim>` argv.
    cmd = _build_nix_command(
        flake_ref="path:/some/flake/dir",
        env_attr="default",
        shim_path=Path("/repo/scripts/shim.py"),
        module_dir=Path("/lab/modules/fig"),
        ctx_json_path=tmp_path / "ctx.json",
    )
    assert cmd[0] == "nix"
    assert "shell" in cmd
    assert "path:/some/flake/dir#default" in cmd
    assert str(Path("/repo/scripts/shim.py")) in cmd
    assert cmd[-2:] == [str(Path("/lab/modules/fig")), str(tmp_path / "ctx.json")]


def test_journey_nix_diamond_through_binary(
    tmp_path: Path, require_nix_build: None
) -> None:
    lab = _copy_lab("nix_diamond", tmp_path)
    proc = subprocess.run(  # noqa: S603 (fixed binary path, test-owned args)
        [str(_DAE), "--json", "lab", "run"],
        cwd=lab,
        capture_output=True,
        text=True,
        env={**os.environ},
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    payload = json.loads(proc.stdout)
    # Success codes carry no "dae." prefix (LAB_RUN_OK); ok_empty does (it is a
    # FAILURE-category sibling reused for the zero-flight case).
    assert payload["code"] in {"dae.lab.run.ok", "dae.lab.run.ok_empty"}

    joined = json.loads(next(lab.glob(".daedalus/**/joined.json")).read_text())
    branches = joined["branches"]
    assert branches["fig"]["my_lib"] == "pyfiglet"
    assert branches["art"]["my_lib"] == "art"
    for branch in branches.values():
        assert branch["sees_sibling_lib"] is False
        assert branch["sees_host_only_networkx"] is False
        assert branch["isolation_marker"] == "nix"


def test_module_with_nothing_to_nixify_is_refused(tmp_path: Path) -> None:
    # A requirements.txt is generated into a lock, so uv.lock is optional; a module
    # with none of flake.nix, uv.lock or requirements.txt has nothing to nixify.
    lab = _copy_lab("nix_diamond", tmp_path)
    fig = lab / "modules" / "fig"
    (fig / "uv.lock").unlink()
    (fig / "requirements.txt").unlink()
    # NixProvisionError, not a bare Exception, which would also accept an unrelated
    # failure. The refusal happens before any build, so no nix_can_build gate.
    with pytest.raises(NixProvisionError, match="nothing to nixify"):
        NixStrategy().provision(fig)


@pytest.mark.skipif(shutil.which("uv") is None, reason="the uv backend needs uv")
def test_uv_and_nix_yield_the_same_lineage(
    tmp_path: Path, require_nix_build: None
) -> None:
    # `isolation: uv` and `isolation: nix` give the same lineage shape (layout, step
    # ids, statuses) even though the backends differ. The fixture ships
    # requirements.txt for uv and pyproject plus uv.lock for nix.
    uv_lab = _run_nix_diamond(
        _copy_lab("nix_diamond", tmp_path / "uv"), isolation="uv"
    )[1]
    nix_lab = _run_nix_diamond(
        _copy_lab("nix_diamond", tmp_path / "nix"), isolation="nix"
    )[1]

    assert _lineage_shape(uv_lab) == _lineage_shape(nix_lab)
    # both completed every step; a lineage of all failed steps would also match.
    assert {status for _id, status in _lineage_shape(nix_lab).values()} == {"completed"}
