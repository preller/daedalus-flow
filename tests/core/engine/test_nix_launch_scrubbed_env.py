"""The nix launch runs under the same scrubbed env as the uv path.

An inherited ``LD_LIBRARY_PATH`` beats a closure's baked search path; no nix run needed.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from daedalus.core.engine import subprocess_runner

if TYPE_CHECKING:
    import pytest

_REPO_ROOT = Path("/repo")
# The dir that exposes only the daedalus package: what a child gets on
# PYTHONPATH. Mirrors subprocess_runner._daedalus_import_root() for a checkout.
_IMPORT_ROOT = _REPO_ROOT / "src"


def test_nix_child_env_strips_ld_library_path_and_pollution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A leaked LD_LIBRARY_PATH (and the pollution set) never reaches the nix child."""
    monkeypatch.setenv("LD_LIBRARY_PATH", "/nix/store/shim/lib")
    monkeypatch.setenv("PYTHONHOME", "/some/pyhome")
    monkeypatch.setenv("VIRTUAL_ENV", "/some/venv")
    monkeypatch.setenv("CONDA_PREFIX", "/some/conda")
    monkeypatch.setenv("UV_PROJECT_ENVIRONMENT", "/some/proj/.venv")
    monkeypatch.setenv("HOME", "/home/me")
    monkeypatch.setenv("PATH", "/closure/bin:/usr/bin")

    env = subprocess_runner._nix_child_env(_IMPORT_ROOT)

    for stripped in (
        "LD_LIBRARY_PATH",
        "PYTHONHOME",
        "VIRTUAL_ENV",
        "CONDA_PREFIX",
        "UV_PROJECT_ENVIRONMENT",
    ):
        assert stripped not in env, f"{stripped} must be scrubbed on the nix path"


def test_nix_child_env_keeps_path_and_sets_pythonpath_and_isolation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PATH survives; PYTHONPATH and ``DAE_ISOLATION`` are set after the scrub."""
    monkeypatch.setenv("HOME", "/home/me")
    monkeypatch.setenv("PATH", "/closure/bin:/usr/bin")
    monkeypatch.setenv("PYTHONPATH", "/host/site-packages")  # must not leak

    env = subprocess_runner._nix_child_env(_IMPORT_ROOT)

    assert env["PATH"] == "/closure/bin:/usr/bin"
    assert env["HOME"] == "/home/me"
    # The import root replaces any inherited PYTHONPATH.
    assert env["PYTHONPATH"] == str(_IMPORT_ROOT)
    assert env["DAE_ISOLATION"] == "nix"


def test_nix_child_env_built_on_shared_clean_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Built on _clean_subprocess_env, so both launch paths share one scrub."""
    monkeypatch.setenv("HOME", "/home/me")
    monkeypatch.setenv("PATH", "/closure/bin")
    calls: list[int] = []
    real_clean = subprocess_runner._clean_subprocess_env

    def spy() -> dict[str, str]:
        calls.append(1)
        return real_clean()

    monkeypatch.setattr(subprocess_runner, "_clean_subprocess_env", spy)

    subprocess_runner._nix_child_env(_IMPORT_ROOT)

    assert calls, "_nix_child_env must build on the shared _clean_subprocess_env"
