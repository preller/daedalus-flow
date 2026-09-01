"""One lab under ``engine: local`` and ``engine: prefect`` writes the same durable data.

Needs the ``[engine]`` extra; Prefect runs in-process with a temp ``PREFECT_HOME``.
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path
from typing import Any, cast

import pytest

# find_spec does not import prefect; the engine imports it at run time, after the
# autouse _prefect_env fixture has set the settings prefect caches at import.
pytestmark = [
    pytest.mark.skipif(
        importlib.util.find_spec("prefect") is None,
        reason="the optional daedalus-flow[engine] extra (prefect) is not installed",
    ),
    pytest.mark.integration,
]

from typer.testing import CliRunner  # noqa: E402

from daedalus.cli import app  # noqa: E402
from tests._helpers import (  # noqa: E402
    chdir,
    copy_parallel_example,
    fixtures_root,
    run_cli_json,
)


@pytest.fixture(autouse=True)
def _prefect_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Ephemeral, quiet Prefect settings, set before the engine imports prefect."""
    home = tmp_path / "prefect_home"
    home.mkdir()
    monkeypatch.setenv("PREFECT_SERVER_ALLOW_EPHEMERAL_MODE", "true")
    monkeypatch.setenv("PREFECT_LOGGING_LEVEL", "CRITICAL")  # keeps --json stdout clean
    monkeypatch.setenv("PREFECT_LOGGING_TO_API_ENABLED", "false")
    monkeypatch.setenv("PREFECT_SERVER_ANALYTICS_ENABLED", "false")
    monkeypatch.setenv("PREFECT_HOME", str(home))


_FLOW_ID_RE = re.compile(r"flow_\d{8}_\d{6}")
# flow_id and duration_s change per run; engine and max_workers differ across the
# compared runs and are asserted separately by _engine_info.
_VOLATILE_KEYS = frozenset({"flow_id", "duration_s", "engine", "max_workers"})


def _copy_linear_smoke(dest: Path, *, engine: str) -> Path:
    """Copy the linear_smoke fixture lab into ``dest`` and set its engine field."""
    import shutil

    lab = dest / f"lab_{engine}"
    shutil.copytree(
        fixtures_root() / "labs" / "linear_smoke",
        lab,
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    if engine != "local":
        lab_yaml = (lab / "lab.yaml").read_text()
        (lab / "lab.yaml").write_text(f"engine: {engine}\n{lab_yaml}")
    return lab


def _copy_parallel(dest: Path, *, engine: str, max_workers: int) -> Path:
    """Copy the ``parallel`` example; each of its modules carries a requirements.txt."""
    return copy_parallel_example(dest, engine=engine, max_workers=max_workers)


def _run(lab: Path) -> dict[str, Any]:
    """Run ``dae --json lab run`` with cwd inside ``lab``; return the parsed payload."""
    return run_cli_json(lab, "lab", "run")


def _norm_path(rel: str) -> str:
    """Replace the volatile flow_id dir component of a flow-relative path."""
    return _FLOW_ID_RE.sub("flow_X", rel)


def _data_files(lab: Path) -> dict[str, bytes]:
    """Durable files under dae-outputs, keyed by normalized path."""
    root = lab / "dae-outputs"
    # dae-flow.json carries per-run ids and times; step.log is the child's live
    # output and is absent on the in-process path.
    skip = {"dae-flow.json", "step.log"}
    return {
        _norm_path(str(p.relative_to(root))): p.read_bytes()
        for p in root.rglob("*")
        if p.is_file() and p.name not in skip
    }


def _strip_volatile(obj: Any) -> Any:
    """Recursively drop volatile fields (flow_id, durations, any *_at timestamp)."""
    if isinstance(obj, dict):
        return {
            k: _strip_volatile(v)
            for k, v in obj.items()
            if k not in _VOLATILE_KEYS and not k.endswith("_at")
        }
    if isinstance(obj, list):
        return [_strip_volatile(v) for v in obj]
    return obj


def _raw_flow_record(lab: Path) -> dict[str, Any]:
    """The single flow record (dae-flow.json), parsed, volatile fields kept."""
    records = list((lab / "dae-outputs" / "flows").rglob("dae-flow.json"))
    assert len(records) == 1, f"expected one flow record, found {records}"
    return cast("dict[str, Any]", json.loads(records[0].read_text()))


def _flow_record(lab: Path) -> Any:
    """The single flow record (dae-flow.json) with volatile fields stripped."""
    return _strip_volatile(_raw_flow_record(lab))


def _engine_info(lab: Path) -> tuple[str, int]:
    """(engine, max_workers) from the flow record; an absent key means the default."""
    raw = _raw_flow_record(lab)
    return str(raw.get("engine", "local")), int(raw.get("max_workers", 1))


@pytest.mark.slow
def test_prefect_matches_local_engine_byte_for_byte(tmp_path: Path) -> None:
    """Same outcome code, same steps, same durable bytes, equal stripped flow record."""
    local_lab = _copy_linear_smoke(tmp_path, engine="local")
    prefect_lab = _copy_linear_smoke(tmp_path, engine="prefect")

    local = _run(local_lab)
    prefect = _run(prefect_lab)

    # 1. same outcome code.
    assert local["code"] == "dae.lab.run.ok"
    assert prefect["code"] == "dae.lab.run.ok"
    # 2. same completed instance set (id + status), order-independent.
    local_steps = {(s["id"], s["status"]) for s in local["data"]["steps"]}
    prefect_steps = {(s["id"], s["status"]) for s in prefect["data"]["steps"]}
    assert prefect_steps == local_steps
    assert all(status == "completed" for _, status in prefect_steps)

    # 3. same durable tree shape (flow-id normalized) and 4. byte-identical data.
    local_files = _data_files(local_lab)
    prefect_files = _data_files(prefect_lab)
    assert set(prefect_files) == set(local_files), "durable tree shape diverged"
    diffs = [k for k in local_files if local_files[k] != prefect_files[k]]
    assert not diffs, f"durable data files differ between engines: {diffs}"

    # 5a. engine and max_workers are stripped from the record equality, so pin them.
    assert _engine_info(local_lab) == ("local", 1)
    assert _engine_info(prefect_lab) == ("prefect", 1)
    # 5b. the flow record matches once volatile fields are stripped.
    assert _flow_record(prefect_lab) == _flow_record(local_lab)


@pytest.mark.slow
def test_conformance_golden_detects_a_data_divergence(tmp_path: Path) -> None:
    """One extra byte in a Prefect output file shows up in the comparison."""
    local_lab = _copy_linear_smoke(tmp_path, engine="local")
    prefect_lab = _copy_linear_smoke(tmp_path, engine="prefect")
    _run(local_lab)
    _run(prefect_lab)

    # Inject a single-byte divergence into one Prefect output file.
    target = next(
        p
        for p in (prefect_lab / "dae-outputs").rglob("*.json")
        if p.name != "dae-flow.json"
    )
    target.write_bytes(target.read_bytes() + b" ")

    local_files = _data_files(local_lab)
    prefect_files = _data_files(prefect_lab)
    diffs = [k for k in local_files if local_files[k] != prefect_files.get(k)]
    assert diffs, "the conformance comparison failed to detect an injected divergence"


@pytest.mark.slow
def test_prefect_k4_matches_local_k1_and_k4_byte_for_byte(tmp_path: Path) -> None:
    """local K=1, local K=4 and prefect K=4 write the same bytes and flow record."""
    local_k1 = _copy_parallel(tmp_path, engine="local", max_workers=1)
    local_k4 = _copy_parallel(tmp_path, engine="local", max_workers=4)
    prefect_k4 = _copy_parallel(tmp_path, engine="prefect", max_workers=4)

    for lab in (local_k1, local_k4, prefect_k4):
        assert _run(lab)["code"] == "dae.lab.run.ok", lab.name

    # engine and max_workers are stripped from the record equality, so pin them here.
    assert _engine_info(local_k1) == ("local", 1)
    assert _engine_info(local_k4) == ("local", 4)
    assert _engine_info(prefect_k4) == ("prefect", 4)

    reference = _data_files(local_k1)
    for lab in (local_k4, prefect_k4):
        files = _data_files(lab)
        assert set(files) == set(reference), (
            f"durable tree shape diverged for {lab.name}"
        )
        diffs = [k for k in reference if reference[k] != files[k]]
        assert not diffs, f"durable data differs for {lab.name}: {diffs}"
        assert _flow_record(lab) == _flow_record(local_k1), lab.name


def _copy_fanout(dest: Path, *, engine: str, max_workers: int) -> Path:
    """Copy the ``ensemble`` example (M=4 flights); prepend engine and max_workers."""
    import shutil

    from tests._helpers import examples_root

    lab = dest / f"ensemble_{engine}_k{max_workers}"
    shutil.copytree(
        examples_root() / "ensemble",
        lab,
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    body = (lab / "lab.yaml").read_text()
    (lab / "lab.yaml").write_text(
        f"engine: {engine}\nmax_workers: {max_workers}\n{body}"
    )
    return lab


@pytest.mark.slow
def test_prefect_fanout_m_gt_1_matches_local_k1_and_k4_byte_for_byte(
    tmp_path: Path,
) -> None:
    """ensemble (M=4) matches across local K=1, local K=4 and prefect K=4."""
    local_k1 = _copy_fanout(tmp_path, engine="local", max_workers=1)
    local_k4 = _copy_fanout(tmp_path, engine="local", max_workers=4)
    prefect_k4 = _copy_fanout(tmp_path, engine="prefect", max_workers=4)

    payloads = {lab.name: _run(lab) for lab in (local_k1, local_k4, prefect_k4)}
    for name, payload in payloads.items():
        assert payload["code"] == "dae.lab.run.ok", name

    # 4 analyze instances, 1 emit and 1 collect, all completed: the collector ran
    # only after every flight finished.
    prefect_steps = payloads[prefect_k4.name]["data"]["steps"]
    assert all(s["status"] == "completed" for s in prefect_steps)
    analyze_instances = [s for s in prefect_steps if s["id"].startswith("analyze@")]
    collect_instances = [s for s in prefect_steps if s["id"].startswith("collect@")]
    assert len(analyze_instances) == 4, prefect_steps  # one per Flight (M=4)
    assert len(collect_instances) == 1, prefect_steps  # the single converging sink

    # engine and max_workers are stripped from the equality below; assert them here.
    assert _engine_info(local_k1) == ("local", 1)
    assert _engine_info(local_k4) == ("local", 4)
    assert _engine_info(prefect_k4) == ("prefect", 4)

    # Byte-identical durable data + stripped flow record across all three runs.
    reference = _data_files(local_k1)
    for lab in (local_k4, prefect_k4):
        files = _data_files(lab)
        assert set(files) == set(reference), (
            f"durable tree shape diverged for {lab.name}"
        )
        diffs = [k for k in reference if reference[k] != files[k]]
        assert not diffs, f"durable data differs for {lab.name}: {diffs}"
        assert _flow_record(lab) == _flow_record(local_k1), lab.name


@pytest.mark.slow
def test_fanout_conformance_golden_detects_a_per_flight_divergence(
    tmp_path: Path,
) -> None:
    """One extra byte in one flight's Prefect output shows up in the comparison."""
    local_lab = _copy_fanout(tmp_path, engine="local", max_workers=4)
    prefect_lab = _copy_fanout(tmp_path, engine="prefect", max_workers=4)
    _run(local_lab)
    _run(prefect_lab)

    # Perturb one per-flight result under the Prefect run.
    target = next(
        p
        for p in (prefect_lab / "dae-outputs").rglob("result.json")
        if p.name != "dae-flow.json"
    )
    target.write_bytes(target.read_bytes() + b" ")

    local_files = _data_files(local_lab)
    prefect_files = _data_files(prefect_lab)
    diffs = [k for k in local_files if local_files[k] != prefect_files.get(k)]
    assert diffs, (
        "the M>1 conformance comparison failed to detect an injected divergence"
    )


@pytest.mark.slow
def test_k4_conformance_detects_a_branch_divergence(tmp_path: Path) -> None:
    """One extra byte in a prefect K=4 branch output shows up against local K=1."""
    local_k1 = _copy_parallel(tmp_path, engine="local", max_workers=1)
    prefect_k4 = _copy_parallel(tmp_path, engine="prefect", max_workers=4)
    _run(local_k1)
    _run(prefect_k4)

    target = next((prefect_k4 / "dae-outputs").rglob("stat.json"))
    target.write_bytes(target.read_bytes() + b" ")

    reference = _data_files(local_k1)
    files = _data_files(prefect_k4)
    diffs = [k for k in reference if reference[k] != files.get(k)]
    assert diffs, (
        "the K=4 conformance comparison failed to detect an injected divergence"
    )


_RAISING_BRANCH = (
    "import daedalus.flow as dae\n\n\n"
    "@dae.entry\n"
    "def stat_min(ctx: dae.FlowContext) -> None:\n"
    '    raise RuntimeError("stat_min raised by the test")\n'
)


def _run_allow_failure(lab: Path) -> dict[str, Any]:
    """Run ``dae --json lab run`` without asserting success; return the payload."""
    runner = CliRunner()
    with chdir(lab):
        result = runner.invoke(app, ["--json", "lab", "run"], prog_name="dae")
    return cast("dict[str, Any]", json.loads(result.output))


@pytest.mark.slow
def test_prefect_failure_matches_local_failure_partial_tree(tmp_path: Path) -> None:
    """A raising branch leaves the same outcome, completed set and partial tree."""
    local = _copy_parallel(tmp_path, engine="local", max_workers=4)
    prefect_lab = _copy_parallel(tmp_path, engine="prefect", max_workers=4)
    for lab in (local, prefect_lab):
        (lab / "modules" / "stat_min" / "main.py").write_text(_RAISING_BRANCH)

    local_run = _run_allow_failure(local)
    prefect_run = _run_allow_failure(prefect_lab)

    # 1. both fail with the same outcome code.
    assert local_run["code"] != "dae.lab.run.ok", local_run
    assert prefect_run["code"] == local_run["code"], (prefect_run, local_run)
    # 2. same completed-instance set: the failed branch + the collector are absent.
    local_done = {
        s["id"] for s in local_run["data"]["steps"] if s["status"] == "completed"
    }
    prefect_done = {
        s["id"] for s in prefect_run["data"]["steps"] if s["status"] == "completed"
    }
    assert prefect_done == local_done, (prefect_done, local_done)
    assert not any(s.startswith("combine@") for s in local_done), local_done
    # 3. byte-identical partial durable tree.
    local_files = _data_files(local)
    prefect_files = _data_files(prefect_lab)
    assert set(prefect_files) == set(local_files), "partial tree shape diverged"
    diffs = [k for k in local_files if local_files[k] != prefect_files[k]]
    assert not diffs, f"partial durable data differs between engines: {diffs}"


def test_settle_one_records_an_unmodeled_exception_as_failed() -> None:
    """A bare RuntimeError from a failed future settles as failed, not as a raise."""
    from types import SimpleNamespace

    from daedalus.core.engine import prefect as pf

    # _record_unexpected_failure touches only these fields, so a SimpleNamespace
    # stands in for _RunState; cast satisfies strict mypy.
    state = SimpleNamespace(
        module_status={"work@w1": "submitted"},
        durations={},
        started_at={},
        finished_at={},
        error=None,
        missing_package=None,
    )

    class _FailedNotReady:
        def is_completed(self) -> bool:
            return False

        def is_failed(self) -> bool:
            return True

    class _CrashingFuture:
        state = _FailedNotReady()

        def result(self, **_kwargs: object) -> object:
            raise RuntimeError("provisioning blew up in the prefect thread")

    pf._settle_one(cast(Any, state), "work@w1", _CrashingFuture())

    assert state.module_status["work@w1"] == "failed"
    assert state.error is not None
    assert "provisioning blew up" in state.error
