"""Run a module in a child interpreter through ``subprocess_runner``.

Skips as a whole without ``uv``; the third-party numpy test never skips alone.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

import daedalus.flow as dae
from daedalus.core.engine import subprocess_runner
from tests._helpers import _step_ctx, _write_module

# Repo root (the editable daedalus source the child imports): tests/ -> repo.
_REPO_ROOT = Path(__file__).resolve().parents[3]
# The dir that exposes only the daedalus package: what a child gets on
# PYTHONPATH. Mirrors subprocess_runner._daedalus_import_root() for a checkout.
_IMPORT_ROOT = _REPO_ROOT / "src"

# Every test needs the launcher, so the whole module skips without uv.
_UV = shutil.which("uv")
pytestmark = [
    pytest.mark.skipif(
        _UV is None, reason="uv launcher not on PATH; subprocess spike needs it"
    ),
    pytest.mark.integration,
]


def test_run_no_dep_module_via_uv_shim_writes_lineage_across_boundary(
    tmp_path: Path,
) -> None:
    """Mirrors linear_smoke's ``emit_ticks``: seed in, ticks.json and manifest out."""
    mod = _write_module(
        tmp_path / "emit_ticks",
        "import json\n\n"
        "import daedalus.flow as dae\n\n\n"
        "@dae.entry\n"
        "def emit_ticks(ctx: dae.FlowContext) -> None:\n"
        "    payload = json.loads((ctx.step_input_path / 'seed.json').read_text())\n"
        "    n = int(payload['n_ticks'])\n"
        "    ticks = [(ctx.seed + i * 7) % 100 for i in range(n)]\n"
        "    (ctx.step_output_path / 'ticks.json').write_text(\n"
        "        json.dumps({'ticks': ticks, 'seed': ctx.seed}, indent=2)\n"
        "    )\n",
        role="emitter",
    )
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "seed.json").write_text(json.dumps({"n_ticks": 3}))
    output_dir = tmp_path / "out"
    ctx = _step_ctx(
        output_dir=output_dir, input_dir=input_dir, role=dae.Role.EMITTER, seed=41
    )

    result = subprocess_runner.run_step_subprocess(mod, ctx, import_root=_IMPORT_ROOT)

    assert result.returncode == 0, result.stderr
    assert result.status == "completed"
    assert result.missing_package is None
    ticks = json.loads((output_dir / "ticks.json").read_text())
    assert ticks == {"ticks": [(41 + i * 7) % 100 for i in range(3)], "seed": 41}
    manifest = json.loads((output_dir / "dae-manifest.json").read_text())
    assert manifest["format_version"] == 1
    assert manifest["status"] == "completed"
    assert manifest["seed"] == 41
    assert manifest["step_id"] == "out"


def test_run_third_party_dep_module_with_ld_library_path_propagation(
    tmp_path: Path,
) -> None:
    """numpy, a C extension, imports in the child under the LD_LIBRARY_PATH shim."""
    mod = _write_module(
        tmp_path / "use_numpy",
        "import json\n\n"
        "import numpy as np\n\n"
        "import daedalus.flow as dae\n\n\n"
        "@dae.entry\n"
        "def use_numpy(ctx: dae.FlowContext) -> None:\n"
        "    rng = np.random.default_rng(ctx.seed)\n"
        "    draws = rng.integers(0, 100, size=4).tolist()\n"
        "    (ctx.step_output_path / 'draws.json').write_text(\n"
        "        json.dumps({'draws': draws, 'numpy': np.__version__})\n"
        "    )\n",
    )
    output_dir = tmp_path / "out"
    ctx = _step_ctx(
        output_dir=output_dir,
        input_dir=tmp_path,
        role=dae.Role.TRANSFORM,
        seed=7,
    )

    result = subprocess_runner.run_step_subprocess(
        mod,
        ctx,
        import_root=_IMPORT_ROOT,
        requirements=("numpy>=1.26",),
    )

    assert result.returncode == 0, result.stderr
    assert result.status == "completed"
    assert result.missing_package is None
    drawn = json.loads((output_dir / "draws.json").read_text())
    assert len(drawn["draws"]) == 4
    manifest = json.loads((output_dir / "dae-manifest.json").read_text())
    assert manifest["status"] == "completed"
    assert manifest["format_version"] == 1


def test_child_nonzero_rc_surfaces_as_failed(tmp_path: Path) -> None:
    """The manifest of a raising entry records status failed and the error text."""
    mod = _write_module(
        tmp_path / "boom",
        "import daedalus.flow as dae\n\n\n"
        "@dae.entry\n"
        "def boom(ctx: dae.FlowContext) -> None:\n"
        "    raise RuntimeError('boom raised in the child')\n",
    )
    output_dir = tmp_path / "out"
    ctx = _step_ctx(
        output_dir=output_dir, input_dir=tmp_path, role=dae.Role.TRANSFORM, seed=1
    )

    result = subprocess_runner.run_step_subprocess(mod, ctx, import_root=_IMPORT_ROOT)

    assert result.returncode != 0
    assert result.status == "failed"
    assert result.missing_package is None
    manifest = json.loads((output_dir / "dae-manifest.json").read_text())
    assert manifest["status"] == "failed"
    assert "boom raised in the child" in (manifest.get("error") or "")


def test_child_writes_no_manifest_is_detected(tmp_path: Path) -> None:
    """A shim that exits 0 without writing a manifest raises SubprocessStepError."""
    mod = _write_module(
        tmp_path / "silent",
        "import daedalus.flow as dae\n\n\n"
        "@dae.entry\n"
        "def silent(ctx: dae.FlowContext) -> None:\n"
        "    pass\n",
    )
    output_dir = tmp_path / "out"
    ctx = _step_ctx(
        output_dir=output_dir, input_dir=tmp_path, role=dae.Role.TRANSFORM, seed=1
    )

    # A shim that exits 0 and writes no manifest.
    no_manifest_shim = tmp_path / "no_manifest_runner.py"
    no_manifest_shim.write_text("import sys\n\nsys.exit(0)\n")

    with pytest.raises(subprocess_runner.SubprocessStepError, match="no .*manifest"):
        subprocess_runner.run_step_subprocess(
            mod, ctx, import_root=_IMPORT_ROOT, shim_path=no_manifest_shim
        )


def test_missing_dae_entry_in_child_surfaces_load_failure(tmp_path: Path) -> None:
    """The child runs the ``load_entry`` marker scan; no entry is a failed step."""
    mod = _write_module(
        tmp_path / "no_entry",
        "import daedalus.flow as dae\n\n\ndef not_an_entry(ctx):\n    pass\n",
    )
    output_dir = tmp_path / "out"
    ctx = _step_ctx(
        output_dir=output_dir, input_dir=tmp_path, role=dae.Role.TRANSFORM, seed=1
    )

    result = subprocess_runner.run_step_subprocess(mod, ctx, import_root=_IMPORT_ROOT)

    assert result.returncode != 0
    assert result.status == "failed"
    assert result.missing_package is None
    manifest = json.loads((output_dir / "dae-manifest.json").read_text())
    assert manifest["status"] == "failed"
    assert "no @dae.entry" in (manifest.get("error") or "")


def test_provisioning_failure_vs_module_raise_classification(tmp_path: Path) -> None:
    """Only an absent top-level package is missing_deps; find_spec runs in the child."""
    out_a = tmp_path / "out_a"
    mod_a = _write_module(
        tmp_path / "absent_pkg",
        "import no_such_pkg_dae_test\n\n"
        "import daedalus.flow as dae\n\n\n"
        "@dae.entry\n"
        "def absent_pkg(ctx: dae.FlowContext) -> None:\n"
        "    pass\n",
    )
    res_a = subprocess_runner.run_step_subprocess(
        mod_a,
        _step_ctx(
            output_dir=out_a, input_dir=tmp_path, role=dae.Role.TRANSFORM, seed=1
        ),
        import_root=_IMPORT_ROOT,
    )
    assert res_a.status == "failed"
    assert res_a.missing_package == "no_such_pkg_dae_test"

    out_b = tmp_path / "out_b"
    mod_b = _write_module(
        tmp_path / "raiser",
        "import daedalus.flow as dae\n\n\n"
        "@dae.entry\n"
        "def raiser(ctx: dae.FlowContext) -> None:\n"
        "    raise RuntimeError('module raised, not a missing dep')\n",
    )
    res_b = subprocess_runner.run_step_subprocess(
        mod_b,
        _step_ctx(
            output_dir=out_b, input_dir=tmp_path, role=dae.Role.TRANSFORM, seed=1
        ),
        import_root=_IMPORT_ROOT,
    )
    assert res_b.status == "failed"
    assert res_b.missing_package is None

    out_c = tmp_path / "out_c"
    mod_c = _write_module(
        tmp_path / "broken_submodule",
        "import json.no_such_submodule_dae_test\n\n"
        "import daedalus.flow as dae\n\n\n"
        "@dae.entry\n"
        "def broken_submodule(ctx: dae.FlowContext) -> None:\n"
        "    pass\n",
    )
    res_c = subprocess_runner.run_step_subprocess(
        mod_c,
        _step_ctx(
            output_dir=out_c, input_dir=tmp_path, role=dae.Role.TRANSFORM, seed=1
        ),
        import_root=_IMPORT_ROOT,
    )
    assert res_c.status == "failed"
    assert res_c.missing_package is None


def test_module_requirements_reads_real_file_and_filters_comments(
    tmp_path: Path,
) -> None:
    """Spec lines keep their order, comments and blanks drop, no file gives []."""
    real = tmp_path / "real"
    real.mkdir()
    (real / "requirements.txt").write_text(
        "# fit dependencies\n\nnumpy>=1.26  # array maths\n  scipy\n"
    )
    assert subprocess_runner._module_requirements(real) == ["numpy>=1.26", "scipy"]

    comment_only = tmp_path / "comment_only"
    comment_only.mkdir()
    (comment_only / "requirements.txt").write_text(
        "# stdlib only (json); no third-party dependencies.\n"
    )
    assert subprocess_runner._module_requirements(comment_only) == []

    absent = tmp_path / "absent"
    absent.mkdir()
    assert subprocess_runner._module_requirements(absent) == []


def test_real_requirements_file_provisions_numpy_without_inline_override(
    tmp_path: Path,
) -> None:
    """The runner reads requirements.txt when no ``requirements=`` kwarg is passed."""
    mod = _write_module(
        tmp_path / "use_numpy_from_file",
        "import json\n\n"
        "import numpy as np\n\n"
        "import daedalus.flow as dae\n\n\n"
        "@dae.entry\n"
        "def use_numpy_from_file(ctx: dae.FlowContext) -> None:\n"
        "    rng = np.random.default_rng(ctx.seed)\n"
        "    (ctx.step_output_path / 'draws.json').write_text(\n"
        "        json.dumps({'draws': rng.integers(0, 100, size=3).tolist()})\n"
        "    )\n",
    )
    (mod / "requirements.txt").write_text("numpy>=1.26\n")
    output_dir = tmp_path / "out"
    ctx = _step_ctx(
        output_dir=output_dir, input_dir=tmp_path, role=dae.Role.TRANSFORM, seed=7
    )

    result = subprocess_runner.run_step_subprocess(mod, ctx, import_root=_IMPORT_ROOT)

    assert result.returncode == 0, result.stderr
    assert result.status == "completed"
    assert result.missing_package is None
    drawn = json.loads((output_dir / "draws.json").read_text())
    assert len(drawn["draws"]) == 3


def test_comment_only_requirements_injects_no_spurious_with(tmp_path: Path) -> None:
    """A comment-only requirements.txt adds no ``--with`` and the module completes."""
    mod = _write_module(
        tmp_path / "stdlib_with_comment_reqs",
        "import json\n\n"
        "import daedalus.flow as dae\n\n\n"
        "@dae.entry\n"
        "def stdlib_with_comment_reqs(ctx: dae.FlowContext) -> None:\n"
        "    (ctx.step_output_path / 'ok.json').write_text(json.dumps({'ok': True}))\n",
    )
    (mod / "requirements.txt").write_text(
        "# stdlib only (json); no third-party dependencies.\n"
    )
    output_dir = tmp_path / "out"
    ctx = _step_ctx(
        output_dir=output_dir, input_dir=tmp_path, role=dae.Role.TRANSFORM, seed=1
    )

    result = subprocess_runner.run_step_subprocess(mod, ctx, import_root=_IMPORT_ROOT)

    assert result.returncode == 0, result.stderr
    assert result.status == "completed"
    assert result.missing_package is None
    assert json.loads((output_dir / "ok.json").read_text()) == {"ok": True}
