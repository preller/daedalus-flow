"""``max_workers`` defaults to 1; opting into parallel provisions uv subprocesses.

An undeclared ambient dependency then fails, which is why parallel stays opt-in.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from daedalus.core.engine.isolation import ModuleEnv, resolve_module
from daedalus.core.engine.protocol import LabConfig

pytestmark = pytest.mark.integration

# A plain module with no declared preference: its strategy is decided by the lab
# default (policy unset, max_workers), so it reads the constructor defaults cleanly.
_PLAIN = ModuleEnv(module="m", preference=("none",))


def test_default_lab_config_runs_serial_ambient() -> None:
    # A LabConfig built with only its required fields runs serially at K=1 with
    # unset isolation, which resolves to in-process ambient.
    config = LabConfig(lab_name="t", lab_dir=Path("."))
    assert config.max_workers == 1
    assert config.isolation is None
    assert (
        resolve_module(_PLAIN, config.isolation, config.max_workers).strategy
        == "ambient"
    )


def test_parallel_opt_in_resolves_to_uv_subprocess() -> None:
    # max_workers > 1 with isolation unset provisions each module in a uv subprocess,
    # so a module must declare its imports; that is why parallel stays opt-in.
    parallel = LabConfig(lab_name="t", lab_dir=Path("."), max_workers=2)
    assert (
        resolve_module(_PLAIN, parallel.isolation, parallel.max_workers).strategy
        == "uv"
    )
