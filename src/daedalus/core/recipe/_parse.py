"""Recipe parsing, from YAML text to the frozen RecipeSpec and RecipeModule shapes.

Holds the closed vocabularies (roles, engines, isolation), the parsed-recipe
dataclasses, :class:`RecipeParseError`, and the ``safe_load`` plus hand checks
that turn ``lab.yaml`` into a sound spec. ``discover_lab`` and
``read_module_role`` live here too. ``_validate`` and ``_plan`` import from this
module, not the reverse. ``import yaml`` stays confined to this module and off
the ``dae --help`` path.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import yaml

from daedalus.flow import Role

if TYPE_CHECKING:
    from pathlib import Path

# The closed set of dae-module.yaml ``role:`` values. A plan step's role is
# checked against this before any lineage is written; an out-of-set role is
# refused as ``dae.lab.run.invalid`` (exit 2) instead of failing mid-run.
_VALID_ROLES = frozenset(role.value for role in Role)

# The emitter role value. ``two_emitters`` counts modules whose lab.yaml role
# is this (``RecipeModule.role``), not the effective run-path role.
_EMITTER_TYPE = "emitter"

# The engines a lab may select via ``engine:``. ``local`` is the in-process
# LocalEngine (default); ``prefect`` is the optional PrefectEngine behind the
# ``daedalus-flow[engine]`` extra, lazy-imported by the selector (cli/commands/lab/).
_VALID_ENGINES = frozenset({"local", "prefect"})
_VALID_ISOLATION = frozenset({"ambient", "uv", "nix"})

# Lab ``isolation:`` is a policy. ``auto`` honors each module's preference;
# ``ambient``, ``uv`` and ``nix`` force one strategy lab-wide; ``fused`` is
# rejected with a v2 pointer. Unset maps to the K-based default in ``resolve_module``.
_VALID_POLICY = _VALID_ISOLATION | {"auto"}

# Module ``isolation:`` is a preference, a single value or a ladder over this
# set in decreasing strength (``none < uv < nix``). ``none`` fuses into the
# lab env; ``ambient`` is a lab strategy name, not a module preference value.
_ISOLATION_STRENGTH = {"none": 0, "uv": 1, "nix": 2}
_VALID_PREF = frozenset(_ISOLATION_STRENGTH)


@dataclass(frozen=True)
class RecipeModule:
    """One module entry from a lab recipe, with its id, depends and declared role."""

    id: str
    depends: tuple[str, ...]
    role: str | None  # lab.yaml role or None; wins over dae-module.yaml at run


@dataclass(frozen=True)
class RecipeSpec:
    """A parsed lab recipe, with name, ordered modules, K knob, engine and isolation."""

    name: str | None
    modules: tuple[RecipeModule, ...]
    max_workers: int = 1  # K; 1 is in-process, >1 runs each step in its own uv env
    engine: str = "local"  # ``local`` or ``prefect``; see _VALID_ENGINES
    isolation: str | None = None  # lab policy; None means the K-based default


class RecipeParseError(Exception):
    """A lab recipe could not be parsed into a sound :class:`RecipeSpec`."""

    def __init__(self, message: str, line: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.line = line  # 1-based source line from a MarkedYAMLError, else None


def _require_str_id(value: Any, *, field: str) -> str:
    """Return ``value`` as a non-empty str id, else raise RecipeParseError."""
    if not isinstance(value, str):
        raise RecipeParseError(
            f"{field} must be a string, got {value!r} ({type(value).__name__})."
        )
    if not value:
        raise RecipeParseError(f"{field} must be a non-empty string.")
    return value


def _coerce_depends(raw: Any, *, module_id: str) -> tuple[str, ...]:
    """Normalize ``depends:`` (``None`` or a list of str ids) into a tuple of ids."""
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise RecipeParseError(
            f"module '{module_id}' depends must be a list, got {type(raw).__name__}."
        )
    return tuple(
        _require_str_id(dep, field=f"module '{module_id}' depend") for dep in raw
    )


def _parse_max_workers(raw: object) -> int:
    """Validate ``max_workers`` as a positive int (default 1); bools are rejected."""
    if raw is None:
        return 1
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise RecipeParseError(
            f"recipe max_workers must be a positive integer, got {type(raw).__name__}."
        )
    if raw < 1:
        raise RecipeParseError(
            f"recipe max_workers must be a positive integer, got {raw}."
        )
    return raw


def _parse_engine(raw: object) -> str:
    """Validate the optional ``engine`` selector, default ``local``."""
    if raw is None:
        return "local"
    if not isinstance(raw, str) or raw not in _VALID_ENGINES:
        shown = raw if isinstance(raw, str) else type(raw).__name__
        raise RecipeParseError(
            f"recipe engine must be one of {sorted(_VALID_ENGINES)}, got {shown!r}."
        )
    return raw


def _parse_isolation(raw: object) -> str | None:
    """Validate the lab ``isolation`` policy; unset stays ``None`` for the K default."""
    if raw is None:
        return None
    if raw == "fused":
        raise RecipeParseError(
            "isolation fused (one shared lab environment) is deferred to v2; it "
            "needs the requirement-merging machinery. Use isolation auto to honor "
            "per-module preferences, or uv or nix, or leave it unset for "
            "ambient at max_workers 1 and uv above 1."
        )
    if not isinstance(raw, str) or raw not in _VALID_POLICY:
        shown = raw if isinstance(raw, str) else type(raw).__name__
        valid = sorted(_VALID_POLICY)
        raise RecipeParseError(
            f"recipe isolation must be one of {valid}, got {shown!r}."
        )
    return raw


def _parse_isolation_pref(raw: object) -> tuple[str, ...]:
    """Parse a module ``isolation`` preference into a ladder, strongest first."""
    items = _coerce_pref_items(raw)
    strengths = [_ISOLATION_STRENGTH[item] for item in items]
    for higher, lower in zip(strengths, strengths[1:], strict=False):
        if higher <= lower:
            raise RecipeParseError(
                f"module isolation ladder {items} must be in strictly decreasing "
                f"strength order (strongest first, no duplicates); strength is "
                f"none < uv < nix."
            )
    return tuple(items)


def _coerce_pref_items(raw: object) -> list[str]:
    """Normalize an ``isolation:`` preference into a non-empty list of valid values."""
    if raw is None:
        return ["none"]
    if isinstance(raw, str):
        items: list[object] = [raw]
    elif isinstance(raw, list):
        if not raw:
            raise RecipeParseError("module isolation ladder must not be empty.")
        items = list(raw)
    else:
        raise RecipeParseError(
            f"module isolation must be a string or a list, got {type(raw).__name__}."
        )
    for item in items:
        if not isinstance(item, str) or item not in _VALID_PREF:
            shown = item if isinstance(item, str) else type(item).__name__
            raise RecipeParseError(
                f"module isolation must be one of {sorted(_VALID_PREF)}, got {shown!r}."
            )
    return [str(item) for item in items]


def read_module_isolation_pref(module_dir: Path) -> tuple[str, ...]:
    """Read the ``isolation:`` ladder from a module's ``dae-module.yaml``.

    Defaults to ``("none",)`` when the field or the mapping is absent. A missing
    manifest or a YAML syntax error raises :class:`RecipeParseError`, which the
    run path maps to ``lab.run.invalid``.
    """
    manifest = module_dir / "dae-module.yaml"
    try:
        text = manifest.read_text()
    except OSError as error:
        raise RecipeParseError(
            f"module manifest not found at {manifest}: {error}."
        ) from error
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError as error:
        mark = getattr(error, "problem_mark", None)
        line = mark.line + 1 if mark is not None else None
        raise RecipeParseError(
            f"module manifest at {manifest} is not valid YAML: {error}", line
        ) from error
    if not isinstance(document, dict):
        return ("none",)
    return _parse_isolation_pref(document.get("isolation"))


def load_recipe_text(text: str) -> RecipeSpec:
    """Parse a lab recipe from YAML text into a frozen :class:`RecipeSpec`.

    Raises :class:`RecipeParseError` on a YAML syntax error, a non-mapping
    document, or a malformed ``modules``, id, depend, ``max_workers``,
    ``engine`` or ``isolation`` value.
    """
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError as error:
        mark = getattr(error, "problem_mark", None)
        line = mark.line + 1 if mark is not None else None
        raise RecipeParseError(f"recipe is not valid YAML: {error}", line) from error

    if document is None:
        return RecipeSpec(name=None, modules=())
    if not isinstance(document, dict):
        raise RecipeParseError(
            f"recipe must be a YAML mapping, got a {type(document).__name__} document."
        )

    name = document.get("name")
    if name is not None and not isinstance(name, str):
        raise RecipeParseError(
            f"recipe name must be a string, got {type(name).__name__}."
        )

    max_workers = _parse_max_workers(document.get("max_workers"))
    engine = _parse_engine(document.get("engine"))
    isolation = _parse_isolation(document.get("isolation"))
    if isolation == "ambient" and max_workers > 1:
        raise RecipeParseError(
            "isolation ambient runs in-process and is not concurrency-safe; it "
            "requires max_workers 1 (use isolation uv for a parallel run)."
        )

    raw_modules = document.get("modules")
    if raw_modules is None:
        return RecipeSpec(
            name=name,
            modules=(),
            max_workers=max_workers,
            engine=engine,
            isolation=isolation,
        )
    if not isinstance(raw_modules, list):
        raise RecipeParseError(
            f"recipe modules must be a list, got {type(raw_modules).__name__}."
        )

    return RecipeSpec(
        name=name,
        modules=_parse_modules(raw_modules),
        max_workers=max_workers,
        engine=engine,
        isolation=isolation,
    )


def _parse_module(entry: Any, seen: set[str]) -> RecipeModule:
    """Validate one raw module mapping into a frozen :class:`RecipeModule`."""
    if not isinstance(entry, dict):
        raise RecipeParseError(
            f"each module must be a mapping, got {type(entry).__name__}."
        )
    module_id = _require_str_id(entry.get("id"), field="module id")
    if module_id in seen:
        raise RecipeParseError(f"duplicate module id '{module_id}'.")
    seen.add(module_id)
    depends = _coerce_depends(entry.get("depends"), module_id=module_id)
    raw_role = entry.get("role")
    if raw_role is not None and not isinstance(raw_role, str):
        raise RecipeParseError(
            f"module '{module_id}' role must be a string, got "
            f"{type(raw_role).__name__}."
        )
    return RecipeModule(id=module_id, depends=depends, role=raw_role)


def _parse_modules(raw_modules: list[Any]) -> tuple[RecipeModule, ...]:
    """Validate the recipe's ``modules:`` list into ordered RecipeModules."""
    seen: set[str] = set()
    return tuple(_parse_module(entry, seen) for entry in raw_modules)


def load_recipe(path: Path) -> RecipeSpec:
    """Read and parse a lab recipe file into a :class:`RecipeSpec`."""
    return load_recipe_text(path.read_text())


def discover_lab(cwd: Path) -> Path | None:
    """Return ``cwd / 'lab.yaml'`` if it is a file, else ``None``.

    ``lab run`` takes the lab from the current directory; ``None`` is the
    "no lab here" result the CLI maps to ``dae.lab.run.not_found``.
    """
    candidate = cwd / "lab.yaml"
    return candidate if candidate.is_file() else None


def read_module_role(module_dir: Path) -> str | None:
    """Read the ``role:`` field from a module dir's ``dae-module.yaml``.

    Returns ``None`` when the field is absent or the manifest is not a mapping.
    A missing manifest file or a YAML syntax error raises RecipeParseError, which
    the run path maps to ``lab.run.invalid`` (exit 2).
    """
    manifest = module_dir / "dae-module.yaml"
    try:
        text = manifest.read_text()
    except OSError as error:
        raise RecipeParseError(
            f"module manifest not found at {manifest}: {error}."
        ) from error
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError as error:
        mark = getattr(error, "problem_mark", None)
        line = mark.line + 1 if mark is not None else None
        raise RecipeParseError(
            f"module manifest at {manifest} is not valid YAML: {error}", line
        ) from error
    if not isinstance(document, dict):
        return None
    role = document.get("role")
    return role if isinstance(role, str) else None
