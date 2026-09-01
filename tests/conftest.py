"""Shared pytest fixtures and the nix build-capability probe.

Helper functions live in tests/_helpers.py; the only third-party import is pytest.
"""

from __future__ import annotations

import functools
import json
import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path

import pytest

# The nix build-probe below needs fixtures_root(); everything else the suite
# imports lives in tests/_helpers.py and is imported there directly.
from tests._helpers import fixtures_root


@pytest.fixture
def out_dir(tmp_path: Path) -> Path:
    """A fresh, created ``out`` directory under the test's ``tmp_path``."""
    d = tmp_path / "out"
    d.mkdir()
    return d


@pytest.fixture
def stage(tmp_path: Path) -> Callable[[str, str, object], Path]:
    """Factory that stages an upstream input file under ``tmp_path``.

    Writes ``obj`` as indented JSON to ``tmp_path/<subdir>/<filename>`` and returns
    the holding directory.
    """

    def _stage(subdir: str, filename: str, obj: object) -> Path:
        d = tmp_path / subdir
        d.mkdir(parents=True, exist_ok=True)
        (d / filename).write_text(json.dumps(obj, indent=2))
        return d

    return _stage


@functools.lru_cache(maxsize=1)
def nix_can_build() -> bool:
    """Whether this host can build a uv2nix flake, probed once per session.

    ``NixStrategy.available()`` only proves ``nix eval`` works; a fetch-only host
    can pass it and still fail ``nix build``. The probe builds the smallest nix
    fixture (``science_nix``) end to end. False means skip, not a code regression.
    """
    from daedalus.core.engine.isolation import NixStrategy

    if not NixStrategy().available():
        return False
    from daedalus.core.engine import LabConfig, LocalEngine
    from daedalus.core.recipe import build_plan, load_recipe

    tmp = Path(tempfile.mkdtemp(prefix="dae_nix_probe_"))
    try:
        lab = tmp / "science_nix"
        shutil.copytree(
            fixtures_root() / "labs" / "science_nix",
            lab,
            ignore=shutil.ignore_patterns("__pycache__"),
        )
        spec = load_recipe(lab / "lab.yaml")
        plan = build_plan(spec, lab)
        config = LabConfig(
            lab_name="science_nix",
            lab_dir=lab,
            seed=0,
            output_root=lab / "dae-outputs",
            max_workers=spec.max_workers,
            isolation="nix",
        )
        result = LocalEngine().execute_dag(plan, config=config)
        return bool(result.status == "completed")
    except Exception:  # noqa: BLE001 (any build/probe failure means: cannot build here)
        return False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture
def require_nix_build() -> None:
    """Skip, not fail, a test when this host cannot build uv2nix flakes.

    For tests that run a ``nix build``; the cheaper ``NixStrategy.available()``
    module gate still skips when nix is absent, this is the build-capability gate.
    """
    if not nix_can_build():
        pytest.skip(
            "this host cannot build uv2nix nix flakes (nix_can_build() is False)"
        )
