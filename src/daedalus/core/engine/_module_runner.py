# /// script
# requires-python = ">=3.12"
# ///
"""The PEP 723 shim run in a child interpreter.

The parent (``subprocess_runner.py``) launches this script with two argv
entries, the module directory and a JSON file holding the FlowContext. The shim
rebuilds the FlowContext, runs the module through the same ``load_entry`` scan
as the in-process engine and writes the terminal ``dae-manifest.json``. A
missing third-party package is reported on stderr as ``DAE_MISSING_PACKAGE=``;
the exit code is 0 only on a completed step. daedalus arrives over ``PYTHONPATH``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import daedalus.flow as dae
from daedalus.core import lineage
from daedalus.core.engine.step import StepError, execute_step

# The out-of-band marker the parent greps for to resolve missing_deps vs failed.
# Kept off the manifest so the lineage record stays a clean human error.
MISSING_PACKAGE_MARKER = "DAE_MISSING_PACKAGE="

_EXPECTED_ARGC = 2  # module_dir + ctx_json


def _load_context(ctx_json_path: Path) -> dae.FlowContext:
    """Reconstruct a FlowContext from the JSON the parent wrote."""
    raw = json.loads(ctx_json_path.read_text())
    return dae.FlowContext(
        step_id=str(raw["step_id"]),
        role=dae.Role(str(raw["role"])),
        step_input_path=Path(raw["step_input_path"]),
        step_output_path=Path(raw["step_output_path"]),
        flight_id=str(raw["flight_id"]),
        walk_id=str(raw["walk_id"]),
        walk_inputs={k: Path(v) for k, v in dict(raw["walk_inputs"]).items()},
        flight_inputs={k: Path(v) for k, v in dict(raw["flight_inputs"]).items()},
        seed=int(raw["seed"]),
    )


def _write_manifest(
    step_dir: Path, step_id: str, seed: int, status: str, error: str | None
) -> None:
    """Write the terminal manifest via the same core writer the engine uses."""
    step_dir.mkdir(parents=True, exist_ok=True)
    lineage.write_step_manifest(
        step_dir,
        lineage.StepManifest(step_id=step_id, status=status, seed=seed, error=error),
    )


def main(argv: list[str]) -> int:
    """Run one module in this child interpreter; write the terminal manifest.

    Returns the process exit code: 0 on a completed step, 1 on any failure, 2 on
    a usage error.
    """
    if len(argv) != _EXPECTED_ARGC:
        sys.stderr.write("usage: _module_runner.py <module_dir> <ctx_json>\n")
        return 2
    module_dir = Path(argv[0])
    ctx = _load_context(Path(argv[1]))

    try:
        execute_step(module_dir, ctx)
    except StepError as error:
        # The child owns the real environment, so it classifies a missing package
        # via load_entry's find_spec check. The marker goes to stderr only and the
        # manifest error stays a plain human string.
        if error.missing_package is not None:
            sys.stderr.write(MISSING_PACKAGE_MARKER + error.missing_package + "\n")
        _write_manifest(
            ctx.step_output_path, ctx.step_id, ctx.seed, "failed", str(error)
        )
        sys.stderr.write(str(error) + "\n")
        return 1
    except Exception as error:  # noqa: BLE001 (any other failure is a failed step)
        _write_manifest(
            ctx.step_output_path, ctx.step_id, ctx.seed, "failed", str(error)
        )
        sys.stderr.write(str(error) + "\n")
        return 1

    _write_manifest(ctx.step_output_path, ctx.step_id, ctx.seed, "completed", None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
