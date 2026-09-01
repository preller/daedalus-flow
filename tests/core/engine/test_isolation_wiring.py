"""The run path resolves isolation per module, not lab-wide.

One flow can mix ambient, uv and nix modules; ``_instance.py`` reads each preference.
"""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

import pytest

from tests.core.engine._local_engine import _copy_diamond_join

if TYPE_CHECKING:
    from pathlib import Path

_UV = shutil.which("uv")

pytestmark = pytest.mark.integration


@pytest.mark.skipif(
    _UV is None, reason="uv launcher needed for the uv-preferring module"
)
def test_heterogeneous_lab_resolves_each_module_per_module(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import daedalus.core.engine.local._instance as inst
    from daedalus.core.engine import LabConfig, LocalEngine
    from daedalus.core.engine.isolation import resolve_module

    plan, config, lab = _copy_diamond_join(tmp_path)
    # One module declares a per-module uv preference; the lab policy stays auto.
    manifest = lab / "modules" / "left" / "dae-module.yaml"
    manifest.write_text(manifest.read_text() + "isolation: uv\n")
    config = LabConfig(
        lab_name="diamond_join",
        lab_dir=lab,
        seed=0,
        output_root=lab / "dae-outputs",
        max_workers=1,
        isolation="auto",
    )

    seen: dict[str, str] = {}
    real_resolve = resolve_module

    def spy(env, policy, max_workers):
        resolution = real_resolve(env, policy, max_workers)
        seen[resolution.module] = resolution.strategy
        return resolution

    monkeypatch.setattr(inst, "resolve_module", spy)

    result = LocalEngine().execute_dag(plan, config=config)

    # Each module resolved to its own strategy, left under uv and the rest ambient.
    assert seen == {
        "seed": "ambient",
        "left": "uv",
        "right": "ambient",
        "join": "ambient",
    }
    # And the heterogeneous lab still completes end to end.
    assert result.status == "completed"
    assert set(result.module_status.values()) == {"completed"}
