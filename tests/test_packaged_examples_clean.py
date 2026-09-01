"""The packaged examples ship no tool caches or bytecode.

Checked on the git index and on a built wheel; the wheel check skips without uv.
"""

from __future__ import annotations

import re
import subprocess
import zipfile
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_EXAMPLES_REL = "src/daedalus/examples"
_CRUFT_RE = re.compile(r"(^|/)(\.mypy_cache|__pycache__)(/|$)|\.pyc$")


def _git_tracked_examples() -> list[str]:
    proc = subprocess.run(  # noqa: S603 (fixed argv, no shell)
        ["git", "ls-files", _EXAMPLES_REL],  # noqa: S607 (git on PATH, test-only)
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return [line for line in proc.stdout.splitlines() if line]


def test_no_cruft_is_git_tracked_under_examples() -> None:
    tracked = _git_tracked_examples()
    # The example tree must be tracked; an empty result would pass vacuously.
    assert tracked, "expected git-tracked files under src/daedalus/examples"
    offenders = [p for p in tracked if _CRUFT_RE.search(p)]
    assert offenders == [], f"dev cruft is git-tracked under examples: {offenders}"


def test_pyproject_excludes_cruft_from_the_wheel() -> None:
    # The hatch wheel target names the cruft globs explicitly, so the wheel stays
    # clean even if .gitignore is disabled.
    text = (_REPO_ROOT / "pyproject.toml").read_text()
    assert "[tool.hatch.build.targets.wheel]" in text
    for pattern in ("**/.mypy_cache", "**/__pycache__", "**/*.pyc"):
        assert pattern in text, f"wheel exclude is missing {pattern!r}"


def test_built_wheel_carries_no_cruft(tmp_path: Path) -> None:
    # Build a wheel into a scratch dir and assert no cache/bytecode rode along.
    try:
        proc = subprocess.run(  # noqa: S603 (fixed argv, no shell)
            [  # noqa: S607 (uv on PATH, test-only)
                "uv",
                "build",
                "--wheel",
                "--out-dir",
                str(tmp_path),
            ],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        pytest.skip("uv is not available to build a wheel on this host")
    if proc.returncode != 0:
        pytest.skip(f"wheel build unavailable on this host: {proc.stderr[-400:]}")

    wheels = list(tmp_path.glob("*.whl"))
    assert len(wheels) == 1, f"expected exactly one wheel, got {wheels}"
    with zipfile.ZipFile(wheels[0]) as zf:
        offenders = [n for n in zf.namelist() if _CRUFT_RE.search(n)]
    assert offenders == [], f"built wheel carries dev cruft: {offenders}"
