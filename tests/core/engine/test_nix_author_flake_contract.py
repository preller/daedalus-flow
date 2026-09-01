"""A module's own committed ``flake.nix`` is the ``isolation: nix`` contract path.

Under ``auto`` it resolves to nix as ``own-flake``, and provision builds that flake.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from daedalus.core.engine.isolation import ModuleEnv, NixStrategy, resolve_module

if TYPE_CHECKING:
    import pytest


def _write_flake_module_with_requirements(module_dir: Path) -> Path:
    """A module with both an author flake.nix and a requirements.txt foil."""
    module_dir.mkdir(parents=True, exist_ok=True)
    (module_dir / "dae-module.yaml").write_text(
        "role: transform\nisolation: [nix, uv]\n"
    )
    (module_dir / "main.py").write_text("import daedalus.flow as dae\n")
    (module_dir / "flake.nix").write_text("{ outputs = _: {}; }\n")
    (module_dir / "flake.lock").write_text("{}\n")
    (module_dir / "requirements.txt").write_text("numpy>=1.26\n")
    return module_dir


def test_flake_module_resolves_to_nix_via_auto_as_own_flake(tmp_path: Path) -> None:
    """The author flake outranks a co-present requirements.txt."""
    module_dir = _write_flake_module_with_requirements(tmp_path / "fit")
    env = ModuleEnv.from_module_dir("fit", module_dir)

    resolution = resolve_module(env, policy="auto", max_workers=1)

    assert resolution.strategy == "nix"
    assert resolution.flake_origin == "own-flake"
    # own-flake is the contract path, so source stays the ladder preference, never
    # the generated marker.
    assert resolution.source != "auto-gen"


def test_provision_builds_author_flake_not_generated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Spies on the three build hooks; only _materialize_own_flake fires."""
    module_dir = _write_flake_module_with_requirements(tmp_path / "fit")

    own_flake_calls: list[Path] = []
    generate_calls: list[Path] = []
    lock_calls: list[Path] = []

    monkeypatch.setattr(
        NixStrategy,
        "_materialize_own_flake",
        lambda self, flake_dir, src, *, log_dir=None: own_flake_calls.append(src),
    )
    monkeypatch.setattr(
        NixStrategy,
        "_generate_and_build",
        lambda self, flake_dir, name, specs, *, log_dir=None: generate_calls.append(
            flake_dir
        ),
    )
    monkeypatch.setattr(
        NixStrategy,
        "_materialize_and_build",
        lambda self, flake_dir, *, pyproject, lock, log_dir=None: lock_calls.append(
            flake_dir
        ),
    )

    NixStrategy().provision(module_dir)

    assert own_flake_calls == [module_dir], "must build the author's own flake.nix"
    assert generate_calls == [], "must not generate a flake from requirements"
    assert lock_calls == [], "must not take the uv.lock template path"
