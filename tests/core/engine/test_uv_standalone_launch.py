"""The uv strategy launches a uv-managed standalone interpreter under a scrubbed env.

Most tests patch subprocess.run; the numpy smoke test runs a real standalone.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest

import daedalus.flow as dae
from daedalus.core.engine import subprocess_runner
from tests._helpers import _step_ctx

if TYPE_CHECKING:
    pass

_REPO_ROOT = Path(__file__).resolve().parents[3]
# The dir that exposes only the daedalus package: what a child gets on
# PYTHONPATH. Mirrors subprocess_runner._daedalus_import_root() for a checkout.
_IMPORT_ROOT = _REPO_ROOT / "src"


def _capture_run(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    """Patch subprocess.run in the runner; capture argv + env, write a manifest."""
    captured: dict[str, object] = {}

    def fake_run(command, *, stdout, stderr, env, check):  # noqa: ANN001
        captured["command"] = list(command)
        captured["env"] = dict(env)
        # The argv ends with: <shim> <module_dir> <ctx_json_path>; the step dir is
        # the ctx_json_path's parent. Write a completed manifest so _run_child can
        # resolve an outcome without a real child.
        step_dir = Path(command[-1]).parent
        _write_completed_manifest(step_dir)
        return _CompletedZero()

    monkeypatch.setattr(subprocess, "run", fake_run)
    return captured


class _CompletedZero:
    """A stand-in for subprocess.CompletedProcess with a clean rc==0."""

    returncode = 0
    stdout = ""
    stderr = ""


def _write_completed_manifest(step_dir: Path) -> None:
    """Write the minimal completed manifest the runner reads back."""
    manifest = {
        "format_version": 1,
        "step_id": step_dir.name,
        "status": "completed",
        "seed": 1,
        "error": None,
    }
    (step_dir / "dae-manifest.json").write_text(json.dumps(manifest))


def test_build_command_uses_standalone_interpreter_flags() -> None:
    """The uv argv carries --managed-python and --no-config (the standalone flags)."""
    cmd = subprocess_runner._build_command(
        shim_path=Path("/shim.py"),
        requirements=(),
        module_dir=Path("/mod"),
        ctx_json_path=Path("/out/dae-context.json"),
    )
    assert "--managed-python" in cmd
    assert "--no-config" in cmd
    # Both flags must precede the --script terminator (they are uv run options).
    script_idx = cmd.index("--script")
    assert cmd.index("--managed-python") < script_idx
    assert cmd.index("--no-config") < script_idx


def test_clean_subprocess_env_strips_pollution_and_sets_managed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The scrubbed env drops the pollution set and keeps ``HOME`` and ``PATH``."""
    monkeypatch.setenv("LD_LIBRARY_PATH", "/nix/store/x/lib")
    monkeypatch.setenv("PYTHONPATH", "/some/site-packages")
    monkeypatch.setenv("VIRTUAL_ENV", "/some/venv")
    monkeypatch.setenv("PYTHONHOME", "/some/pyhome")
    monkeypatch.setenv("CONDA_PREFIX", "/some/conda")
    monkeypatch.setenv("CONDA_DEFAULT_ENV", "base")
    monkeypatch.setenv("UV_PROJECT", "/some/proj")
    monkeypatch.setenv("UV_PROJECT_ENVIRONMENT", "/some/proj/.venv")
    # A dev shell may pin `UV_PYTHON` at a nix interpreter; it must not override the
    # child's `UV_MANAGED_PYTHON=1`.
    monkeypatch.setenv("UV_PYTHON", "/nix/store/x/bin/python3.12")
    monkeypatch.setenv("HOME", "/home/me")
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    monkeypatch.setenv("UV_CACHE_DIR", "/cache/uv")
    monkeypatch.setenv("XDG_CACHE_HOME", "/cache/xdg")

    env = subprocess_runner._clean_subprocess_env()

    for stripped in (
        "LD_LIBRARY_PATH",
        "PYTHONPATH",
        "VIRTUAL_ENV",
        "PYTHONHOME",
        "CONDA_PREFIX",
        "CONDA_DEFAULT_ENV",
        "UV_PROJECT",
        "UV_PROJECT_ENVIRONMENT",
        "UV_PYTHON",
    ):
        assert stripped not in env, f"{stripped} must be scrubbed"

    assert env["HOME"] == "/home/me"
    assert env["PATH"] == "/usr/bin:/bin"
    assert env["UV_CACHE_DIR"] == "/cache/uv"
    assert env["XDG_CACHE_HOME"] == "/cache/xdg"
    assert env["UV_MANAGED_PYTHON"] == "1"


def test_run_step_subprocess_launches_under_scrubbed_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The launch path uses the scrubbed env, with no inherited LD_LIBRARY_PATH."""
    monkeypatch.setenv("LD_LIBRARY_PATH", "/nix/store/x/lib")
    monkeypatch.setenv("VIRTUAL_ENV", "/some/venv")
    monkeypatch.setenv("HOME", "/home/me")
    captured = _capture_run(monkeypatch)

    mod = tmp_path / "mod"
    mod.mkdir()
    (mod / "dae-module.yaml").write_text("role: transform\n")
    output_dir = tmp_path / "out"
    ctx = _step_ctx(
        output_dir=output_dir, input_dir=tmp_path, role=dae.Role.TRANSFORM, seed=1
    )

    subprocess_runner.run_step_subprocess(mod, ctx, import_root=_IMPORT_ROOT)

    env = cast("dict[str, str]", captured["env"])
    assert "LD_LIBRARY_PATH" not in env
    assert "VIRTUAL_ENV" not in env
    assert env["UV_MANAGED_PYTHON"] == "1"
    command = cast("list[str]", captured["command"])
    assert "--managed-python" in command
    assert "--no-config" in command


# A python-build-standalone version that is download-only on a typical host, so a
# host-discovered nix python on PATH cannot shadow it. The manylinux wheel then
# loads against the host glibc with no LD_LIBRARY_PATH shim.
_STANDALONE_PIN = "3.13.5"


@pytest.mark.slow
@pytest.mark.integration
def test_numpy_imports_shim_free_on_standalone_interpreter(tmp_path: Path) -> None:
    """numpy's C extension loads on the standalone interpreter with no shim."""
    if shutil.which("uv") is None:
        pytest.skip("uv launcher not on PATH; standalone smoke needs it")

    smoke = tmp_path / "numpy_smoke.py"
    smoke.write_text(
        "# /// script\n"
        '# requires-python = ">=3.12"\n'
        '# dependencies = ["numpy>=1.26"]\n'
        "# ///\n"
        "import numpy as np\n"
        'print("numpy ok", np.__version__, int(np.arange(5).sum()))\n'
    )

    # The shipped argv plus an explicit standalone pin (see _STANDALONE_PIN).
    command = [
        "uv",
        "run",
        "--managed-python",
        "--python",
        _STANDALONE_PIN,
        "--no-config",
        "--no-project",
        "--with",
        "numpy>=1.26",
        "--script",
        str(smoke),
    ]
    # LD_LIBRARY_PATH is stripped, so a pass cannot come from the shim.
    child_env = {k: v for k, v in os.environ.items() if k != "LD_LIBRARY_PATH"}

    completed = subprocess.run(  # noqa: S603 (fixed argv, no shell)
        command,
        capture_output=True,
        text=True,
        env=child_env,
        check=False,
        timeout=300,
    )

    # With no cache and no network the standalone cannot be provisioned; when the
    # failure is not the numpy load under test, skip rather than fake a pass.
    provision_failed = (
        completed.returncode != 0
        and "Downloading" not in completed.stderr
        and "libstdc++" not in completed.stderr
        and "numpy" not in completed.stderr
    )
    if provision_failed:
        pytest.skip(
            "standalone interpreter unavailable offline; host-deferred "
            f"(rc={completed.returncode}): {completed.stderr[-400:]}"
        )

    assert completed.returncode == 0, (
        "numpy must import shim-free on the standalone interpreter; "
        f"stderr:\n{completed.stderr}"
    )
    assert "numpy ok" in completed.stdout, completed.stdout
