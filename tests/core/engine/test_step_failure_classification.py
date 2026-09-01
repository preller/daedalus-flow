"""``classify_step_failure`` maps a step failure to its ``dae.step.*`` code.

A step never loaded, loaded then raised, or had its worker die; the classifier is total.
"""

from __future__ import annotations

from daedalus.core.engine.step import classify_step_failure
from daedalus.core.outcomes import Outcome


def test_missing_package_is_a_load_failure() -> None:
    """An absent third-party import is a load failure; the step never ran."""
    code = classify_step_failure(
        "failed to load step from main.py: No module named 'numpy'",
        missing_package="numpy",
    )
    assert code is Outcome.DAE_STEP_LOAD_FAILED


def test_load_marker_message_is_a_load_failure() -> None:
    """A ``failed to load step`` message without a package signal is a load failure."""
    code = classify_step_failure("failed to load step: @dae.entry missing in main.py")
    assert code is Outcome.DAE_STEP_LOAD_FAILED


def test_dlopen_failure_in_stderr_is_a_load_failure() -> None:
    """A native-lib dlopen failure (cannot open shared object) is a load failure."""
    code = classify_step_failure(
        "subprocess step failed",
        stderr="libfoo.so.1: cannot open shared object file: No such file or directory",
    )
    assert code is Outcome.DAE_STEP_LOAD_FAILED


def test_negative_returncode_is_a_worker_failure() -> None:
    """A negative returncode, a signal kill, is a worker failure."""
    code = classify_step_failure("subprocess step failed", returncode=-9, stderr="")
    assert code is Outcome.DAE_STEP_WORKER_FAILED


def test_bare_broken_pipe_is_a_worker_failure() -> None:
    """A bare BrokenPipe with no module ``raised`` marker is a worker failure."""
    code = classify_step_failure("BrokenPipeError: [Errno 32] Broken pipe")
    assert code is Outcome.DAE_STEP_WORKER_FAILED


def test_module_raise_is_an_execution_failure() -> None:
    """A normal ``step X raised ...`` message is an execution failure (it loaded)."""
    code = classify_step_failure("step work@w2 raised ValueError: bad value")
    assert code is Outcome.DAE_STEP_EXECUTION_FAILED


def test_empty_input_classifies_without_raising() -> None:
    """Empty input falls through to execution_failed and never raises."""
    code = classify_step_failure("")
    assert code is Outcome.DAE_STEP_EXECUTION_FAILED


def test_raise_marker_beats_broken_pipe() -> None:
    """The ``raised`` marker means the module ran, even for a BrokenPipe exception."""
    code = classify_step_failure("step work@w1 raised BrokenPipeError: Broken pipe")
    assert code is Outcome.DAE_STEP_EXECUTION_FAILED
