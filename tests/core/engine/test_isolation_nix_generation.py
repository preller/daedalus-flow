"""NixStrategy provisioning from a module's own flake.nix or from requirements.txt.

The pure tests run anywhere; the real builds are gated on ``require_nix_build``.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

_TEMPLATE = Path(__file__).resolve().parents[3] / ("src/daedalus/core/engine/nix")
_FIXTURE_FIG = (
    Path(__file__).resolve().parents[2] / "fixtures/labs/nix_diamond/modules/fig"
)


def _copy_fig(dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        _FIXTURE_FIG, dest / "fig", ignore=shutil.ignore_patterns("__pycache__")
    )
    return dest / "fig"


def test_flake_dir_differs_for_own_flake_vs_template(tmp_path: Path) -> None:
    from daedalus.core.engine.isolation import _module_flake_dir

    plain = _copy_fig(tmp_path / "plain")
    owned = _copy_fig(tmp_path / "owned")
    shutil.copy(_TEMPLATE / "flake.nix", owned / "flake.nix")

    assert _module_flake_dir(plain) != _module_flake_dir(owned)


def test_flake_dir_keys_on_requirements_when_no_lock(tmp_path: Path) -> None:
    from daedalus.core.engine.isolation import _module_flake_dir

    a = _copy_fig(tmp_path / "a")
    b = _copy_fig(tmp_path / "b")
    for mod in (a, b):
        (mod / "uv.lock").unlink()
        (mod / "pyproject.toml").unlink()
    (a / "requirements.txt").write_text("pyfiglet>=1,<2\n")
    (b / "requirements.txt").write_text("numpy>=1.26\n")

    assert _module_flake_dir(a) != _module_flake_dir(b)
    # Same requirements -> same dir (stable across the network-dependent lock).
    (b / "requirements.txt").write_text("pyfiglet>=1,<2\n")
    assert _module_flake_dir(a) == _module_flake_dir(b)


def test_generated_pyproject_has_name_deps_and_requires_python() -> None:
    from daedalus.core.engine.isolation import _render_generated_pyproject

    text = _render_generated_pyproject("myfit", ["pyfiglet>=1,<2", "numpy>=1.26"])
    assert 'name = "myfit"' in text
    assert "requires-python" in text
    assert '"pyfiglet>=1,<2"' in text
    assert '"numpy>=1.26"' in text


def test_provision_stages_own_flake_when_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import daedalus.core.engine.isolation as iso

    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    module = _copy_fig(tmp_path / "m")
    (module / "flake.nix").write_text("# the module's own flake\n")

    monkeypatch.setattr(iso, "_nix_build", lambda *a, **k: None)
    iso.NixStrategy().provision(module)

    flake_dir = iso._module_flake_dir(module)
    assert (flake_dir / "flake.nix").read_text() == "# the module's own flake\n"


def test_provision_stages_template_when_no_own_flake(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import daedalus.core.engine.isolation as iso

    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    module = _copy_fig(tmp_path / "m")  # ships pyproject + uv.lock, no flake.nix

    monkeypatch.setattr(iso, "_nix_build", lambda *a, **k: None)
    iso.NixStrategy().provision(module)

    flake_dir = iso._module_flake_dir(module)
    template = (_TEMPLATE / "flake.nix").read_text()
    assert (flake_dir / "flake.nix").read_text() == template


def test_generation_runs_uv_lock_once_cached_behind_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import daedalus.core.engine.isolation as iso

    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    module = _copy_fig(tmp_path / "m")
    (module / "uv.lock").unlink()
    (module / "pyproject.toml").unlink()
    (module / "requirements.txt").write_text("pyfiglet>=1,<2\n")

    calls = {"lock": 0}

    def fake_lock(work_dir: Path) -> None:
        calls["lock"] += 1
        (work_dir / "uv.lock").write_text("# generated lock\n")

    monkeypatch.setattr(iso, "_run_uv_lock", fake_lock)
    monkeypatch.setattr(iso, "_nix_build", lambda *a, **k: None)

    iso.NixStrategy().provision(module)
    iso.NixStrategy().provision(module)  # warm, the marker short-circuits

    assert calls["lock"] == 1


def test_own_flake_module_builds_via_its_own_flake(
    tmp_path: Path, require_nix_build: None
) -> None:
    from daedalus.core.engine.isolation import (
        _PROVISIONED_MARKER,
        NixStrategy,
        _module_flake_dir,
    )

    module = _copy_fig(tmp_path / "m")
    # Give the module its own flake, the stock template content beside it.
    shutil.copy(_TEMPLATE / "flake.nix", module / "flake.nix")
    shutil.copy(_TEMPLATE / "flake.lock", module / "flake.lock")

    NixStrategy().provision(module)

    flake_dir = _module_flake_dir(module)
    assert (flake_dir / _PROVISIONED_MARKER).is_file()
    assert (flake_dir / "flake.nix").read_text() == (module / "flake.nix").read_text()


def test_requirements_only_module_generates_and_builds(
    tmp_path: Path, require_nix_build: None
) -> None:
    from daedalus.core.engine.isolation import (
        _PROVISIONED_MARKER,
        NixStrategy,
        _module_flake_dir,
    )

    module = _copy_fig(tmp_path / "m")
    (module / "uv.lock").unlink()
    (module / "pyproject.toml").unlink()
    (module / "requirements.txt").write_text("pyfiglet>=1,<2\n")

    NixStrategy().provision(module)  # generates pyproject + uv.lock, then builds

    flake_dir = _module_flake_dir(module)
    assert (flake_dir / _PROVISIONED_MARKER).is_file()
    assert (flake_dir / "uv.lock").is_file()  # the generated lock was published
