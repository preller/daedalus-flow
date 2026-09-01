"""Every advertised example completes its full journey through the installed ``dae``.

Expected values come from user-side artifacts; no skip or xfail in this tier.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path
from typing import Literal, NamedTuple

import pytest
import yaml

from daedalus.cli import strings
from tests.journey._journey import _TIMEOUT_S, DAE, _dae, _env, _scaffold

# The journey tier drives the installed `dae` binary over every example, the
# slowest suite. The `e2e` mark lets an inner loop deselect it; the default gate
# still runs it, and it stays out of `slow` because no real sampler runs.
pytestmark = pytest.mark.e2e

# Marker argv for the one step that is not a `dae --json` call: the printed
# `Next:` line, a shell command run verbatim from the scaffold parent. Only its
# exit code is asserted.
NEXT_HINT = "<printed-next-hint>"

# On-disk effects checked after the (exit, code) step: visualize ids equal the
# scaffolded lab.yaml's module ids; a completed run left a non-empty final/;
# no dae-outputs/ after a refusal, a dry run or clean.
Effect = Literal["ids_match_lab_yaml", "no_outputs", "run_artifacts"]


class Step(NamedTuple):
    """One ordered command invocation in an example's journey."""

    argv: tuple[str, ...]  # dae argv without the binary, or (NEXT_HINT,)
    exit_code: int
    code: str | None  # expected --json code; None for the human-mode hint
    effect: Effect | None = None


# Steps are ordered: validate and visualize first, run before flow status, lab
# clean last. demo runs end to end under the walk engine, branching at
# emit_targets and joining at compare_methods, through the installed binary.

# The deterministic journey leaves out module try and module convert (extra
# inputs) and flow resume (a stub with no resumable state). example, lab init
# and module create are scaffolders, not post-scaffold lifecycle.
EXAMPLE_JOURNEYS: dict[str, tuple[Step, ...]] = {
    "minimal": (
        Step(("lab", "validate"), 0, "dae.lab.validate.ok"),
        Step(("lab", "visualize"), 0, "dae.lab.visualize.ok", "ids_match_lab_yaml"),
        Step(("lab", "run", "--dry-run"), 0, "dae.lab.run.dry_run", "no_outputs"),
        Step((NEXT_HINT,), 0, None),
        Step(("lab", "run"), 0, "dae.lab.run.ok", "run_artifacts"),
        Step(("flow", "status"), 0, "dae.flow.status.ok"),
        Step(("lab", "clean"), 0, "dae.lab.clean.ok", "no_outputs"),
    ),
    "complex": (
        Step(("lab", "validate"), 0, "dae.lab.validate.ok"),
        Step(("lab", "visualize"), 0, "dae.lab.visualize.ok", "ids_match_lab_yaml"),
        Step(("lab", "run", "--dry-run"), 0, "dae.lab.run.dry_run", "no_outputs"),
        Step((NEXT_HINT,), 0, None),
        Step(("lab", "run"), 0, "dae.lab.run.ok", "run_artifacts"),
        Step(("flow", "status"), 0, "dae.flow.status.ok"),
        Step(("lab", "clean"), 0, "dae.lab.clean.ok", "no_outputs"),
    ),
    "demo": (
        Step(("lab", "validate"), 0, "dae.lab.validate.ok"),
        Step(("lab", "visualize"), 0, "dae.lab.visualize.ok", "ids_match_lab_yaml"),
        Step(("lab", "run", "--dry-run"), 0, "dae.lab.run.dry_run", "no_outputs"),
        Step((NEXT_HINT,), 0, None),
        Step(("lab", "run"), 0, "dae.lab.run.ok", "run_artifacts"),
        Step(("flow", "status"), 0, "dae.flow.status.ok"),
        Step(("lab", "clean"), 0, "dae.lab.clean.ok", "no_outputs"),
    ),
    # ensemble fans one input across many targets. The per-flight count is
    # pinned in test_journey_fanout, since the closed Effect set cannot express
    # it.
    "ensemble": (
        Step(("lab", "validate"), 0, "dae.lab.validate.ok"),
        Step(("lab", "visualize"), 0, "dae.lab.visualize.ok", "ids_match_lab_yaml"),
        Step(("lab", "run", "--dry-run"), 0, "dae.lab.run.dry_run", "no_outputs"),
        Step((NEXT_HINT,), 0, None),
        Step(("lab", "run"), 0, "dae.lab.run.ok", "run_artifacts"),
        Step(("flow", "status"), 0, "dae.flow.status.ok"),
        Step(("lab", "clean"), 0, "dae.lab.clean.ok", "no_outputs"),
    ),
    # parallel fans a brancher (split) to four sleep transforms joined by one
    # walk_collector (combine). It ships `engine: local` and `max_workers: 1`, so
    # the journey stays serial; the K>1 ordering is pinned in the timing tests.
    "parallel": (
        Step(("lab", "validate"), 0, "dae.lab.validate.ok"),
        Step(("lab", "visualize"), 0, "dae.lab.visualize.ok", "ids_match_lab_yaml"),
        Step(("lab", "run", "--dry-run"), 0, "dae.lab.run.dry_run", "no_outputs"),
        Step((NEXT_HINT,), 0, None),
        Step(("lab", "run"), 0, "dae.lab.run.ok", "run_artifacts"),
        Step(("flow", "status"), 0, "dae.flow.status.ok"),
        Step(("lab", "clean"), 0, "dae.lab.clean.ok", "no_outputs"),
    ),
    # isolation-nix pins two pyfiglet versions in two render branches, one nix
    # env per module. The real run needs a build-capable nix, so this journey
    # stops at the dry run; test_isolation_nix_example.py covers the nix run.
    "isolation-nix": (
        Step(("lab", "validate"), 0, "dae.lab.validate.ok"),
        Step(("lab", "visualize"), 0, "dae.lab.visualize.ok", "ids_match_lab_yaml"),
        Step(("lab", "run", "--dry-run"), 0, "dae.lab.run.dry_run", "no_outputs"),
        Step((NEXT_HINT,), 0, None),
        Step(("flow", "status"), 0, "dae.flow.status.nothing"),
        Step(("lab", "clean"), 0, "dae.lab.clean.nothing", "no_outputs"),
    ),
}

# Core lifecycle every example's journey must cover. Keys are argv with flags
# stripped, so `lab run --dry-run` also counts as (lab, run).
REQUIRED_LIFECYCLE: frozenset[tuple[str, ...]] = frozenset(
    {
        ("lab", "validate"),
        ("lab", "visualize"),
        ("lab", "run"),
        ("flow", "status"),
        ("lab", "clean"),
        (NEXT_HINT,),
    }
)


def _module_ids(lab_dir: Path) -> set[str]:
    """Module ids from the scaffolded lab.yaml (the user-side artifact)."""
    spec = yaml.safe_load((lab_dir / "lab.yaml").read_text())
    ids = {m["id"] for m in spec["modules"]}
    assert ids, f"scaffolded {lab_dir / 'lab.yaml'} lists no modules"
    return ids


def _assert_run_artifacts(lab_dir: Path, stdout: str) -> None:
    payload = json.loads(stdout)["data"]  # unwrap the envelope
    assert payload["status"] == "completed", stdout
    assert all(s["status"] == "completed" for s in payload["steps"]), stdout
    flows = sorted((lab_dir / "dae-outputs" / "flows").iterdir())
    assert flows, "completed run left no flow on disk"
    out = flows[-1] / "final"
    assert out.is_dir() and any(out.iterdir()), "no user-facing final/ results"


def _assert_effect(lab_dir: Path, step: Step, stdout: str) -> None:
    if step.effect == "no_outputs":
        # neither dae-outputs/ nor the .daedalus/ run-once store may survive: a
        # dry run writes nothing and `lab clean` sweeps both.
        for root in ("dae-outputs", ".daedalus"):
            assert not (lab_dir / root).exists(), (
                f"dae {' '.join(step.argv)} must leave no {root}/ behind"
            )
    elif step.effect == "ids_match_lab_yaml":
        rendered = {n["id"] for n in json.loads(stdout)["data"]["topology"]["nodes"]}
        assert rendered == _module_ids(lab_dir), (
            f"visualize rendered {sorted(rendered)!r}, not the scaffolded lab"
        )
    elif step.effect == "run_artifacts":
        _assert_run_artifacts(lab_dir, stdout)


def _run_hint(parent: Path, hint: str) -> None:
    """Run the printed ``Next:`` line verbatim through the shell."""
    proc = subprocess.run(  # noqa: S602 (the promise is a shell line; verbatim)
        hint,
        shell=True,
        cwd=parent,
        env=_env(),
        capture_output=True,
        text=True,
        timeout=_TIMEOUT_S,
        check=False,
    )
    assert proc.returncode == 0, (
        f"the printed Next hint failed: {hint!r}\n{proc.stderr}"
    )


@pytest.mark.parametrize("name", strings.AVAILABLE_EXAMPLES)
def test_example_journey(tmp_path: Path, name: str) -> None:
    """Every step of the example's ordered journey matches its pinned contract."""
    hint = _scaffold(tmp_path, name)
    lab_dir = tmp_path / name
    for step in EXAMPLE_JOURNEYS[name]:
        if step.argv == (NEXT_HINT,):
            _run_hint(tmp_path, hint)
            continue
        exit_code, code, stdout = _dae(lab_dir, *step.argv)
        assert (exit_code, code) == (step.exit_code, step.code), (
            f"{name}: dae {' '.join(step.argv)} -> ({exit_code}, {code!r}), "
            f"expected ({step.exit_code}, {step.code!r})\n{stdout}"
        )
        _assert_effect(lab_dir, step, stdout)


@pytest.mark.parametrize("name", strings.AVAILABLE_EXAMPLES)
def test_every_module_validates(tmp_path: Path, name: str) -> None:
    """Module ids come from the scaffolded lab.yaml, so a new module enrols itself."""
    _scaffold(tmp_path, name)
    lab_dir = tmp_path / name
    for module_id in sorted(_module_ids(lab_dir)):
        exit_code, code, stdout = _dae(lab_dir, "module", "validate", module_id)
        assert (exit_code, code) == (0, "dae.module.validate.ok"), (
            f"{name}: module validate {module_id} -> ({exit_code}, {code!r})\n{stdout}"
        )


@pytest.mark.parametrize("name", strings.AVAILABLE_EXAMPLES)
def test_journey_covers_core_lifecycle(name: str) -> None:
    """An example with no journey is KeyError-red; a thin journey is assert-red."""
    steps = EXAMPLE_JOURNEYS[name]  # KeyError = unenrolled example, red
    present = {
        tuple(tok for tok in step.argv if not tok.startswith("-")) for step in steps
    }
    missing = REQUIRED_LIFECYCLE - present
    assert not missing, (
        f"journey for {name!r} is missing core lifecycle commands: "
        f"{sorted(' '.join(c) for c in missing)}"
    )


@pytest.mark.parametrize("name", strings.AVAILABLE_EXAMPLES)
def test_visualize_style_full_lists_every_module_or_hints_viz(
    tmp_path: Path, name: str
) -> None:
    """With grandalf the DAG lists every module; without it, the viz install hint."""
    _scaffold(tmp_path, name)
    lab_dir = tmp_path / name
    proc = subprocess.run(  # noqa: S603 (fixed binary path, test-owned args)
        [str(DAE), "lab", "visualize", "--style", "full"],
        cwd=lab_dir,
        env=_env(),
        capture_output=True,
        text=True,
        timeout=_TIMEOUT_S,
        check=False,
    )
    assert proc.returncode == 0, (
        f"{name}: visualize --style full exited {proc.returncode}\n{proc.stderr}"
    )
    assert "Traceback" not in proc.stderr, (
        f"{name}: visualize --style full raised\n{proc.stderr}"
    )
    if importlib.util.find_spec("grandalf") is not None:
        missing = sorted(mod for mod in _module_ids(lab_dir) if mod not in proc.stdout)
        assert not missing, (
            f"{name}: visualize --style full omitted {missing}\n{proc.stdout}"
        )
    else:
        assert "viz" in proc.stderr and "pip install" in proc.stderr, (
            f"{name}: visualize --style full gave no install hint\n{proc.stderr}"
        )
