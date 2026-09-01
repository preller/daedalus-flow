"""Isolated steps run from an installed wheel, not only from a checkout.

Builds a wheel, installs it into a throwaway venv and drives the installed dae.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import venv
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e

_REPO_ROOT = Path(__file__).resolve().parents[1]
# The fallback daedalus.__init__ uses when no distribution metadata is found; an
# installed run must never record it.
_UNVERSIONED = "0.0.0.dev0"
_TIMEOUT_S = 600


def _bin(venv_dir: Path, name: str) -> Path:
    """The path to *name* inside *venv_dir*, under ``bin`` or Windows ``Scripts``."""
    sub = "Scripts" if sys.platform == "win32" else "bin"
    suffix = ".exe" if sys.platform == "win32" else ""
    return venv_dir / sub / f"{name}{suffix}"


def _run(
    argv: list[str], *, cwd: Path, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 (fixed argv, no shell)
        argv,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=_TIMEOUT_S,
    )


def _sandboxed_env(tmp_path: Path) -> dict[str, str]:
    """The parent env with the cache redirected into the test's own tmp dir."""
    # Otherwise each run stages an import root into ~/.cache/daedalus/import-roots.
    return {**os.environ, "XDG_CACHE_HOME": str(tmp_path / "xdg-cache")}


@pytest.fixture(scope="module")
def installed_dae(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A throwaway venv with a freshly built daedalus wheel installed in it.

    Skips only when uv is absent. A build that exits nonzero or a wheel that
    will not install is a packaging regression and fails.
    """
    work = tmp_path_factory.mktemp("installed-wheel")
    dist = work / "dist"
    try:
        build = _run(["uv", "build", "--wheel", "--out-dir", str(dist)], cwd=_REPO_ROOT)
    except FileNotFoundError:
        pytest.skip("uv is not available to build a wheel on this host")
    assert build.returncode == 0, f"wheel build failed:\n{build.stderr[-2000:]}"

    wheels = list(dist.glob("*.whl"))
    assert len(wheels) == 1, f"expected exactly one wheel, got {wheels}"

    venv_dir = work / "venv"
    # uv's relocatable 3.13 loses its libpython when copied; a symlink keeps it.
    venv.create(venv_dir, with_pip=True, clear=True, symlinks=sys.platform != "win32")
    install = _run(
        [str(_bin(venv_dir, "python")), "-m", "pip", "install", "-q", str(wheels[0])],
        cwd=work,
    )
    assert install.returncode == 0, f"wheel install failed:\n{install.stderr[-2000:]}"

    dae = _bin(venv_dir, "dae")
    assert dae.exists(), f"the installed wheel exposes no dae entry point at {dae}"
    return dae


def test_parallel_lab_runs_from_an_installed_wheel(
    installed_dae: Path, tmp_path: Path
) -> None:
    """uv once refused ``<venv>/lib/pythonX.Y`` as an editable install target."""
    env = _sandboxed_env(tmp_path)
    scaffold = _run([str(installed_dae), "example", "parallel"], cwd=tmp_path, env=env)
    assert scaffold.returncode == 0, scaffold.stderr

    lab_dir = tmp_path / "parallel"
    lab_yaml = lab_dir / "lab.yaml"
    patched, count = re.subn(
        r"(?m)^max_workers:.*$", "max_workers: 2", lab_yaml.read_text()
    )
    assert count == 1, "expected exactly one max_workers line to raise"
    lab_yaml.write_text(patched)

    run = _run([str(installed_dae), "lab", "run"], cwd=lab_dir, env=env)

    assert run.returncode == 0, (
        f"parallel run failed from an installed wheel\n"
        f"stdout:\n{run.stdout[-2000:]}\nstderr:\n{run.stderr[-2000:]}"
    )
    combined = run.stdout + run.stderr
    assert "completed" in combined, combined[-2000:]
    # "completed" is printed under any strategy and does not show which one ran.
    # Pin the runner's own artifacts instead: step.log files exist only when
    # _run_child launched real children,
    step_logs = list(lab_dir.rglob("step.log"))
    assert step_logs, "no step.log anywhere: the subprocess runner did not run"
    # and the installed (site-packages) layout must have been staged into the
    # import-root cache redirected into this test's tmp dir.
    staged_roots = tmp_path / "xdg-cache" / "daedalus" / "import-roots"
    assert staged_roots.is_dir() and any(staged_roots.iterdir()), (
        "the installed layout was never staged into an isolated import root"
    )


def test_installed_run_records_its_real_version(
    installed_dae: Path, tmp_path: Path
) -> None:
    """daedalus_version resolves from distribution metadata, not the fallback."""
    env = _sandboxed_env(tmp_path)
    scaffold = _run([str(installed_dae), "example", "minimal"], cwd=tmp_path, env=env)
    assert scaffold.returncode == 0, scaffold.stderr

    lab_dir = tmp_path / "minimal"
    run = _run([str(installed_dae), "lab", "run"], cwd=lab_dir, env=env)
    assert run.returncode == 0, run.stderr

    records = sorted(lab_dir.glob("dae-outputs/flows/*/dae-flow.json"))
    assert records, "the run wrote no flow record to read back"
    recorded = json.loads(records[-1].read_text())["daedalus_version"]
    assert recorded != _UNVERSIONED, (
        "an installed run recorded the no-metadata fallback version"
    )
    assert recorded, "the flow record carries no daedalus_version"
