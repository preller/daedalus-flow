"""solve, science_nix: transform that solves a small linear system with scipy.linalg under isolation nix."""

import json
import os
import sys

import numpy as np
import scipy
from scipy import linalg

import daedalus.flow as dae


@dae.entry
def solve(ctx: dae.FlowContext) -> None:
    a = np.array([[3.0, 1.0], [1.0, 2.0]])
    b = np.array([9.0, 8.0])
    x = linalg.solve(a, b)
    residual = float(np.linalg.norm(a @ x - b))
    report = {
        "python": sys.version.split()[0],
        "numpy": np.__version__,
        "scipy": scipy.__version__,
        "solution": x.tolist(),
        "residual_norm": residual,
        # The nix child runs without LD_LIBRARY_PATH; True means the parent shim leaked in.
        "ld_library_path_set": bool(os.environ.get("LD_LIBRARY_PATH")),
        "isolation_marker": os.environ.get("DAE_ISOLATION"),
    }
    (ctx.step_output_path / "result.json").write_text(json.dumps(report, indent=2))
