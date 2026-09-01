"""Both env builders set ``PYTHONSAFEPATH=1``, so the shim's dir never leads sys.path.

Without it engine internals beside the shim shadow top-level names such as ``prefect``.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from daedalus.core.engine import subprocess_runner

if TYPE_CHECKING:
    from collections.abc import Callable

_BUILDERS: list[Callable[[Path], dict[str, str]]] = [
    subprocess_runner._child_env,
    subprocess_runner._nix_child_env,
]


def _import_root(tmp_path: Path) -> Path:
    """A minimal qualifying import root (a fake ``daedalus`` and nothing else)."""
    root = tmp_path / "root"
    (root / "daedalus").mkdir(parents=True)
    (root / "daedalus" / "__init__.py").write_text("")
    return root


@pytest.mark.parametrize("builder", _BUILDERS)
def test_child_env_sets_safe_path(
    builder: Callable[[Path], dict[str, str]], tmp_path: Path
) -> None:
    """Both launch paths must ask the child interpreter for safe-path semantics."""
    env = builder(_import_root(tmp_path))
    assert env["PYTHONSAFEPATH"] == "1"


@pytest.mark.parametrize("builder", _BUILDERS)
def test_script_dir_sibling_is_not_importable(
    builder: Callable[[Path], dict[str, str]], tmp_path: Path
) -> None:
    """A real child sees no decoy beside the script, and ``import daedalus`` works."""
    script_dir = tmp_path / "scripts"
    script_dir.mkdir()
    (script_dir / "dae_decoy_sibling.py").write_text(
        "raise AssertionError('script-dir sibling was importable')\n"
    )
    script = script_dir / "shim.py"
    script.write_text(
        "import importlib.util\n"
        "assert importlib.util.find_spec('dae_decoy_sibling') is None, (\n"
        "    'the script dir leaked onto sys.path'\n"
        ")\n"
        "import daedalus\n"
    )

    env = builder(_import_root(tmp_path))
    completed = subprocess.run(  # noqa: S603 (fixed argv, no shell)
        [sys.executable, str(script)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
