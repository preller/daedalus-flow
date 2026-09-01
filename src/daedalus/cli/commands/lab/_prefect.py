"""Prefect-engine glue for ``dae lab run``.

``_execute_and_resolve`` calls these helpers to quiet Prefect under ``--json``
(stdout is a machine contract) and to announce the slow lazy import in human
mode. They also print the post-run engine, flow and dashboard notes. Each is a
no-op for the LocalEngine, and nothing here imports the command package back.
"""

from __future__ import annotations

import os

from daedalus.cli import chrome, strings
from daedalus.cli.commands._outcome import is_json
from daedalus.core.engine.protocol import ExecutionResult, LabConfig


def _quiet_prefect_for_json(config: LabConfig) -> None:
    """Silence Prefect logging under ``--json`` so its logs never hit stdout."""
    # Hard set, not setdefault; os.environ persists across in-process invocations.
    if config.engine == "prefect" and is_json():
        os.environ["PREFECT_LOGGING_LEVEL"] = "CRITICAL"


def _announce_prefect_start(config: LabConfig) -> None:
    """Print the starting note before the slow prefect import (human mode only)."""
    if config.engine == "prefect" and not is_json():
        chrome.note(strings.PREFECT_STARTING)


def _prefect_ui_url() -> str | None:
    """The Prefect dashboard URL from ``PREFECT_API_URL`` (minus ``/api``), or None."""
    api = os.environ.get("PREFECT_API_URL")
    if not api:
        return None
    return api[: -len("/api")] if api.endswith("/api") else api


def _print_prefect_run_notes(config: LabConfig, result: ExecutionResult) -> None:
    """Print the engine, flow and dashboard notes after a prefect run."""
    if config.engine != "prefect":
        return
    chrome.note(strings.PREFECT_ENGINE_NOTE.format(flow_id=result.flow_id))
    ui_url = _prefect_ui_url()
    chrome.note(
        strings.PREFECT_UI_LIVE.format(url=ui_url)
        if ui_url is not None
        else strings.PREFECT_UI_HINT
    )
