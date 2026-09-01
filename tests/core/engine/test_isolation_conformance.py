"""Unset ``isolation`` equals ambient, and uv at K=1 reaches the in-process tree.

``isolation: ambient`` with ``max_workers > 1`` is refused at parse time.
"""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING, cast

import pytest

from tests.core.engine._local_engine import _copy_diamond_join
from tests.core.engine.test_bounded_parallel import _canonical_tree

if TYPE_CHECKING:
    from pathlib import Path

_UV = shutil.which("uv")

pytestmark = pytest.mark.integration


def _run_diamond(tmp_path: Path, *, max_workers: int, isolation: str | None) -> Path:
    """Run diamond_join under LocalEngine at a given K + isolation; return the lab."""
    from daedalus.core.engine import LabConfig, LocalEngine

    plan, config, lab = _copy_diamond_join(tmp_path)
    config = LabConfig(
        lab_name=config.lab_name,
        lab_dir=config.lab_dir,
        seed=config.seed,
        output_root=config.output_root,
        max_workers=max_workers,
        isolation=isolation,
    )
    LocalEngine().execute_dag(plan, config=config)
    return cast("Path", lab)


def test_unset_equals_explicit_ambient_in_process(tmp_path: Path) -> None:
    # the same lab, isolation unset and explicitly ambient, both at K=1.
    unset = _run_diamond(tmp_path / "unset", max_workers=1, isolation=None)
    ambient = _run_diamond(tmp_path / "ambient", max_workers=1, isolation="ambient")

    # adding the field changed nothing for existing labs.
    assert _canonical_tree(unset) == _canonical_tree(ambient)


@pytest.mark.skipif(
    _UV is None, reason="uv launcher not on PATH; the uv strategy needs it"
)
def test_uv_at_k1_reaches_the_inprocess_default_tree(tmp_path: Path) -> None:
    # `isolation: uv` forces the subprocess path even at K=1; the bounded-parallel
    # golden proves in-process equals subprocess, so the same tree comes back.
    default = _run_diamond(tmp_path / "default", max_workers=1, isolation=None)
    uv = _run_diamond(tmp_path / "uv", max_workers=1, isolation="uv")

    assert _canonical_tree(default) == _canonical_tree(uv)


def test_ambient_with_parallel_is_refused() -> None:
    # ambient is in-process, and the K>1 scheduler would load modules concurrently
    # in one interpreter, so the combination is a parse error.
    from daedalus.core.recipe import RecipeParseError, load_recipe_text

    text = 'name: "t"\nisolation: "ambient"\nmax_workers: 2\nmodules:\n  - id: a\n'
    with pytest.raises(RecipeParseError):
        load_recipe_text(text)


def test_safe_isolation_combos_parse() -> None:
    # every concurrency-safe combination still parses.
    from daedalus.core.recipe import load_recipe_text

    safe = (
        'name: "t"\nisolation: "uv"\nmax_workers: 4\nmodules:\n  - id: a\n',
        'name: "t"\nisolation: "uv"\nmax_workers: 1\nmodules:\n  - id: a\n',
        'name: "t"\nisolation: "ambient"\nmax_workers: 1\nmodules:\n  - id: a\n',
        'name: "t"\nmax_workers: 4\nmodules:\n  - id: a\n',
    )
    for text in safe:
        load_recipe_text(text)  # must not raise
