"""Backend-neutral single-step execution shared by the engine and the tests.

A step is one ``@dae.entry`` function: :func:`load_entry` imports it from its
``main.py``, :func:`build_context` builds the FlowContext, and
:func:`execute_step` pre-creates the output dir and calls it. Nothing here
records lineage, timing or outcome codes; those belong to the engine
(``core/engine/local/``) and the CLI.
"""

from __future__ import annotations

import hashlib
import importlib.util
import sys
from collections.abc import Callable
from pathlib import Path
from typing import cast

import daedalus.flow as dae
from daedalus.core.outcomes import Outcome


class StepError(Exception):
    """A step failed to load or raised while running."""

    def __init__(
        self,
        message: str,
        *,
        missing_package: str | None = None,
        returncode: int | None = None,
        stderr: str = "",
    ) -> None:
        super().__init__(message)
        # These stay off the message so the lineage record keeps a plain human
        # error. missing_package is the absent top-level package on a load
        # failure; returncode and stderr come from a subprocess worker, else unset.
        self.missing_package = missing_package
        self.returncode = returncode
        self.stderr = stderr


# Message and stderr markers meaning the module never loaded, from a top-level
# import error, a missing entry point or a native-lib dlopen failure.
_LOAD_MARKERS = (
    "failed to load step",
    "ImportError",
    "ModuleNotFoundError",
    "cannot open shared object file",
)

# The substring that means a module ran far enough to raise: execute_step wraps a
# module exception as "step <id> raised <Type>: <msg>".
_RAISE_MARKER = "raised"


def classify_step_failure(
    error_message: str,
    *,
    missing_package: str | None = None,
    returncode: int | None = None,
    stderr: str = "",
) -> Outcome:
    """Map one step failure to its ``dae.step.*`` code, ``execution_failed`` by default.

    ``load_failed`` when the module never ran, on a missing package or a load
    marker in the message or stderr. ``worker_failed`` when the worker died, on a
    negative rc or a bare ``BrokenPipeError`` the module did not raise.
    """
    haystack = f"{error_message}\n{stderr}"
    if missing_package is not None or any(
        marker in haystack for marker in _LOAD_MARKERS
    ):
        return Outcome.DAE_STEP_LOAD_FAILED
    if returncode is not None and returncode < 0:
        return Outcome.DAE_STEP_WORKER_FAILED
    if "BrokenPipeError" in error_message and _RAISE_MARKER not in error_message:
        return Outcome.DAE_STEP_WORKER_FAILED
    return Outcome.DAE_STEP_EXECUTION_FAILED


def _is_missing_package(top: str) -> bool:
    """True when ``top`` is absent from the active environment."""
    # An importable top-level package with a broken or missing submodule is a code
    # bug, not an uninstalled dependency. find_spec raising for an absent parent
    # likewise reports not-missing, so the raw error surfaces.
    try:
        return importlib.util.find_spec(top) is None
    except ModuleNotFoundError:
        return False


def load_entry(main_path: Path) -> Callable[[dae.FlowContext], None]:
    """Import ``main.py`` by file path and return its ``@dae.entry`` callable.

    The module is registered in ``sys.modules`` under ``<dir>_main`` before
    ``exec_module`` runs, which dataclass field resolution requires. A missing
    spec, a broken ``main.py`` or no entry callable raises :class:`StepError`.
    """
    # TODO: a ProcessPool backend would need to re-import in the worker.
    main_path = Path(main_path)
    module_name = f"{main_path.parent.name}_main"
    spec = importlib.util.spec_from_file_location(module_name, main_path)
    if spec is None or spec.loader is None:
        raise StepError(
            f"failed to load step from {main_path}: cannot load module spec"
        )
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except ModuleNotFoundError as error:
        top = (error.name or "").split(".")[0]
        if top and not top.startswith("daedalus") and _is_missing_package(top):
            # An absent third-party top-level package sets the missing-deps
            # signal; the message stays a plain human error with no internal tag.
            raise StepError(
                f"failed to load step from {main_path}: No module named {top!r}",
                missing_package=top,
            ) from error
        # name=None (failed relative import), a daedalus-internal import error, or
        # an installed-but-broken package / missing submodule: a real bug, not an
        # uninstalled dependency. Surface it raw as a generic load failure.
        raise StepError(f"failed to load step from {main_path}: {error}") from error
    except Exception as error:  # noqa: BLE001 (any import-time failure is a load failure)
        raise StepError(f"failed to load step from {main_path}: {error}") from error
    for value in vars(module).values():
        if callable(value) and getattr(value, "__daedalus_entry__", False):
            # Module attributes are Any; the @dae.entry marker guarantees a
            # FlowContext entry callable, hence the cast.
            return cast("Callable[[dae.FlowContext], None]", value)
    raise StepError(f"failed to load step from {main_path}: no @dae.entry found")


def derive_seed(flow_seed: int, instance_id: str) -> int:
    """Derive a per-instance 32-bit seed from the flow seed and the instance id.

    sha256 keeps it stable across processes and platforms, unlike the salted
    built-in ``hash()``. ``instance_id`` is ``"<module>@w<id>"``; the bare module
    form is still accepted.
    """
    digest = hashlib.sha256(f"{flow_seed}:{instance_id}".encode()).digest()
    return int.from_bytes(digest[:4], "big")


def build_context(  # noqa: PLR0913 (one keyword argument per FlowContext field)
    *,
    step_id: str,
    role: dae.Role,
    output_dir: Path,
    input_dir: Path | None = None,
    walk_inputs: dict[str, Path] | None = None,
    flight_inputs: dict[str, Path] | None = None,
    flight_id: str = "flight_1",
    walk_id: str = "walk_1",
    seed: int = 0,
) -> dae.FlowContext:
    """Build the :class:`~daedalus.flow.FlowContext` for one step call.

    Emitter and transform read ``step_input_path``; the two collector roles read
    ``walk_inputs`` or ``flight_inputs``. ``flight_1`` and ``walk_1`` are the defaults
    off the fan-out axis. Without ``input_dir`` the input path is ``output_dir``.
    """
    return dae.FlowContext(
        step_id=step_id,
        role=role,
        step_input_path=Path(input_dir) if input_dir is not None else Path(output_dir),
        step_output_path=Path(output_dir),
        flight_id=flight_id,
        walk_id=walk_id,
        walk_inputs=dict(walk_inputs or {}),
        flight_inputs=dict(flight_inputs or {}),
        seed=seed,
    )


def execute_step(module_dir: Path, ctx: dae.FlowContext) -> None:
    """Load ``module_dir/main.py``, pre-create the output dir and call ``entry(ctx)``.

    Records no lineage and measures no time. A load failure raises
    :class:`StepError` ("failed to load step ..."); an exception from the entry is
    wrapped as :class:`StepError` ("step ... raised ...") so both cases share one type.
    """
    module_dir = Path(module_dir)
    entry = load_entry(module_dir / "main.py")
    ctx.step_output_path.mkdir(parents=True, exist_ok=True)
    try:
        entry(ctx)
    except Exception as error:  # noqa: BLE001 (any module error is a step failure)
        raise StepError(
            f"step {ctx.step_id} raised {type(error).__name__}: {error}"
        ) from error
