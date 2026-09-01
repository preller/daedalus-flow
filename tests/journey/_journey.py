"""Journey-tier helpers shared by more than one test file; pytest does not collect it.

Expected values come from user-side artifacts; ``daedalus.core`` is not imported.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

DAE = Path(sys.executable).parent / "dae"
NEXT_LINE = re.compile(r"^Next:\s*(?P<cmd>.+?)\s*$", re.MULTILINE)
# One ceiling for every installed-binary call in the journey tier.
_TIMEOUT_S = 300


def _env() -> dict[str, str]:
    env = os.environ.copy()  # carries the LD_LIBRARY_PATH gcc-lib/libz shim
    env["PATH"] = f"{DAE.parent}{os.pathsep}{env.get('PATH', '')}"
    return env


def _dae(cwd: Path, *args: str) -> tuple[int, str | None, str]:
    """Run the installed binary with --json; return (exit, code, stdout)."""
    # A non-JSON or code-less stdout is a contract violation, raised as a hard
    # failure rather than passed on as code=None.
    assert DAE.exists(), f"installed binary missing at {DAE}; journey tier cannot run"
    proc = subprocess.run(  # noqa: S603 (fixed binary path, test-owned args)
        [str(DAE), "--json", *args],
        cwd=cwd,
        env=_env(),
        capture_output=True,
        text=True,
        timeout=_TIMEOUT_S,
        check=False,
    )
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        msg = (
            f"dae --json {' '.join(args)} emitted non-JSON stdout (exit "
            f"{proc.returncode}); the --json contract is broken:\n"
            f"stdout={proc.stdout!r}\nstderr={proc.stderr!r}"
        )
        raise AssertionError(msg) from exc
    if not isinstance(payload, dict) or "code" not in payload:
        msg = (
            f"dae --json {' '.join(args)} emitted a JSON payload with no 'code' "
            f"key (exit {proc.returncode}); expected a code envelope, got:\n"
            f"{payload!r}"
        )
        raise AssertionError(msg)
    code: str | None = payload["code"]
    return proc.returncode, code, proc.stdout


def _scaffold(tmp_path: Path, name: str) -> str:
    """Scaffold in human mode; return the single printed Next: hint."""
    proc = subprocess.run(  # noqa: S603 (fixed binary path, test-owned args)
        [str(DAE), "example", name],
        cwd=tmp_path,
        env=_env(),
        capture_output=True,
        text=True,
        timeout=_TIMEOUT_S,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert (tmp_path / name / "lab.yaml").is_file()
    hints = NEXT_LINE.findall(proc.stderr)
    assert len(hints) == 1, f"expected exactly one Next hint, got {hints!r}"
    return hints[0]


def _copy_fixture_lab(name: str, dest_parent: Path) -> Path:
    """Copy fixtures/labs/<name> into ``dest_parent``, skipping ``__pycache__``."""
    # Fixtures are addressed by path, not through daedalus.core, and they are
    # not shipped in the wheel.
    dest_parent.mkdir(parents=True, exist_ok=True)
    src = Path(__file__).parents[1] / "fixtures" / "labs" / name
    dest = dest_parent / name
    shutil.copytree(src, dest, ignore=shutil.ignore_patterns("__pycache__"))
    return dest


def _only_flow(lab_dir: Path) -> Path:
    """The single flow dir under a lab's dae-outputs/flows/ (exactly one run)."""
    flows = sorted(
        p for p in (lab_dir / "dae-outputs" / "flows").iterdir() if p.is_dir()
    )
    assert len(flows) == 1, f"expected exactly one flow, found {flows}"
    return flows[0]


def _data_paths(flow: Path) -> list[str]:
    """Sorted relative paths of every non-dae-* leaf file under a flow dir."""
    # dae-* records embed timestamps and durations, so only data files count.
    return sorted(
        str(p.relative_to(flow))
        for p in flow.rglob("*")
        if p.is_file() and not p.name.startswith("dae-")
    )


def _data_hashes(flow: Path) -> dict[str, str]:
    """sha256 of every data file under a flow dir, keyed by relative path."""
    return {
        path: hashlib.sha256((flow / path).read_bytes()).hexdigest()
        for path in _data_paths(flow)
    }
