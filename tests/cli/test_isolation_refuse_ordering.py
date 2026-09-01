"""An unavailable isolation backend refuses before any build or write.

The host-independent twin of the nix-gated guard in test_isolation_nix.py.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from typer.testing import CliRunner

from daedalus.cli.app import app
from daedalus.core.engine.isolation import NixStrategy
from daedalus.core.outcomes import Outcome
from tests._helpers import _copy_lab

if TYPE_CHECKING:
    import pytest


def test_isolation_refusal_precedes_any_build_or_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With nix unavailable, dae-outputs stays absent and provision never runs."""
    monkeypatch.setattr(NixStrategy, "available", lambda self: False)

    provision_calls: list[Path] = []
    real_provision = NixStrategy.provision

    def spy_provision(self: NixStrategy, module_dir: Path):  # noqa: ANN202
        provision_calls.append(Path(module_dir))
        return real_provision(self, module_dir)

    monkeypatch.setattr(NixStrategy, "provision", spy_provision)

    lab = _copy_lab("nix_diamond", tmp_path)
    monkeypatch.chdir(lab)

    result = CliRunner().invoke(app, ["--json", "lab", "run"], prog_name="dae")
    payload = json.loads(result.stdout)

    assert result.exit_code == 1
    assert payload["code"] == Outcome.DAE_LAB_RUN_ISOLATION_UNAVAILABLE.value
    # The whole dae-outputs tree is absent, not only flows/, since the refusal
    # came before any output directory was created.
    assert not (lab / "dae-outputs").exists()
    # No closure build was attempted; the refusal precedes provision.
    assert provision_calls == [], (
        f"provision must not run before the refusal; got {provision_calls}"
    )
