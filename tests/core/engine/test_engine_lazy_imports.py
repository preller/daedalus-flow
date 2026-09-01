"""The ``core/engine`` child import probe and the engine Protocol shape."""

from __future__ import annotations

import subprocess
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from daedalus.core.engine import OrchestrationEngine

# prefect.py is not re-exported, so the probe imports it by name to enforce the
# lazy import. lineage and engine.step are what the nix child shim loads in a
# bare closure, so psutil, an orchestration-only dep, must stay lazy there.
_ISOLATION_PROBE = (
    "import daedalus, daedalus.flow, daedalus.cli, daedalus.core.engine\n"
    "import daedalus.core.engine.prefect\n"
    "from daedalus.core import lineage\n"
    "from daedalus.core.engine.step import StepError, execute_step, load_entry\n"
    "import sys\n"
    "assert 'prefect' not in sys.modules and 'networkx' not in sys.modules\n"
    "assert 'psutil' not in sys.modules, 'psutil leaked into the stdlib child'\n"
)


def _takes_engine(e: OrchestrationEngine) -> None:
    """Accept any structural ``OrchestrationEngine``; mypy is the real check."""


def test_child_imports_keep_prefect_networkx_psutil_lazy() -> None:
    """Runs in a subprocess, so sys.modules is clean; pins the psutil leak fix."""
    result = subprocess.run(  # noqa: S603 (fixed argv: sys.executable + -c probe)
        [sys.executable, "-c", _ISOLATION_PROBE],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"import isolation probe failed:\n{result.stderr}"


def test_local_engine_constructs_and_is_typed() -> None:
    """The callable loop makes the Protocol check fail at runtime, not only in mypy."""
    from daedalus.core.engine import LocalEngine

    engine = LocalEngine()
    _takes_engine(engine)
    # Every Protocol method is present and callable. Resume is outside the Protocol;
    # the CLI resumes through the LocalEngine-specific resume_flow.
    for method in ("execute_dag", "get_status"):
        assert callable(getattr(engine, method, None)), (
            f"LocalEngine is missing the Protocol method {method!r}"
        )
    assert callable(getattr(engine, "resume_flow", None)), (
        "LocalEngine is missing resume_flow, which the CLI flow resume calls"
    )
