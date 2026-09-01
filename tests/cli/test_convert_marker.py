"""``module convert`` plants the same unresolved marker ``module create`` does.

A converted module the author has not wired fails at run time, exit 1, like create.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.cli._cli_contract import (
    FAILURE_EXIT,
    OK_EXIT,
    _copy_fixture_lab,
    _run_cli_in,
)

pytestmark = pytest.mark.integration  # integration tier, CLI command chain

# A trivial script; pasted live with no marker it would run to completion and
# write nothing, and the flow would report completed.
_TRIVIAL_SCRIPT = 'print("converted body ran")\n'


def test_converted_unwired_module_fails_the_run(tmp_path: Path) -> None:
    """An unedited converted module appended to linear_smoke fails the run."""
    lab = _copy_fixture_lab("linear_smoke", tmp_path)
    (lab / "legacy_step.py").write_text(_TRIVIAL_SCRIPT)

    # Convert in the lab cwd so modules/legacy_step/ lands beside the others; the
    # result is left as generated, since the user has not wired it yet.
    convert_exit, convert_code = _run_cli_in(lab, "module", "convert", "legacy_step.py")
    assert (convert_exit, convert_code) == (OK_EXIT, "dae.module.convert.ok")

    # Append the unwired module as a final transform after the flight collector.
    lab_yaml = (lab / "lab.yaml").read_text()
    lab_yaml += "\n  - id: legacy_step\n    depends: [collect_report]\n"
    (lab / "lab.yaml").write_text(lab_yaml)

    # The marker raises at run time, so the flow fails with exit 1.
    assert _run_cli_in(lab, "lab", "run") == (FAILURE_EXIT, "dae.lab.run.failed")


def test_converted_main_carries_the_same_marker_as_create(tmp_path: Path) -> None:
    """The marker text matches create's stub; the pasted body survives beside it."""
    from daedalus.cli.commands.module import _module_stub

    lab = _copy_fixture_lab("linear_smoke", tmp_path)
    (lab / "legacy_step.py").write_text(_TRIVIAL_SCRIPT)
    _run_cli_in(lab, "module", "convert", "legacy_step.py")

    main_text = (lab / "modules" / "legacy_step" / "main.py").read_text()
    marker = 'raise NotImplementedError(f"{ctx.step_id}: implement this module")'

    assert marker in main_text  # the unresolved marker is present
    assert marker in _module_stub("legacy_step")  # identical to create's marker
    assert "converted body ran" in main_text  # the pasted script body survives
