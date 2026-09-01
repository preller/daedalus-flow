"""Bundled-content readers and cwd-relative write-side path builders.

The read side resolves bundled example content inside the wheel under
``daedalus/examples/`` via ``importlib.resources``, whether installed, zipped,
or run from a source checkout. The write side builds the cwd-relative target
paths the mutating verbs scaffold into and copies a bundle out of the wheel.
Every write target is anchored at ``Path.cwd()``, so a command only touches
the directory the user ran it in; the two clean roots come off ``topology``.
"""

import shutil
from importlib.resources import as_file, files
from importlib.resources.abc import Traversable
from pathlib import Path

from daedalus.core import topology


def examples_root() -> Traversable:
    """Traversable for the in-wheel ``daedalus/examples/`` bundle root."""
    return files("daedalus") / "examples"


def example_file(name: str, *parts: str) -> Traversable:
    """Traversable for a file under a named example bundle.

    For example ``example_file("minimal", "lab.yaml")``.
    """
    return examples_root().joinpath(name, *parts)


# Write-side builders. All anchored at the current working directory.


def is_within_cwd(target: Path) -> bool:
    """True only when ``target`` resolves to a path inside the current directory.

    An absolute name makes ``Path.cwd() / name`` discard the cwd and ``..``
    segments climb out of it, so ``/etc/x`` or ``../sibling`` is refused
    before any directory is created.
    """
    try:
        target.resolve().relative_to(Path.cwd().resolve())
        return True
    except ValueError:
        return False


def lab_dir(name: str) -> Path:
    """The cwd-relative directory ``lab init <name>`` scaffolds into."""
    return Path.cwd() / name


def module_dir(name: str) -> Path:
    """The cwd-relative directory ``module create <name>`` scaffolds into."""
    return Path.cwd() / "modules" / name


def example_dir(name: str) -> Path:
    """The cwd-relative directory ``example <name>`` scaffolds a bundle into."""
    return Path.cwd() / name


def clean_roots() -> list[Path]:
    """The two cwd-relative roots ``lab clean`` is allowed to remove."""
    return [Path.cwd() / topology.INTERNAL_DIR, Path.cwd() / topology.OUTPUT_ROOT]


def copy_example_bundle(name: str, dest: Path) -> None:
    """Copy a bundled example tree into ``dest`` (which must not yet exist).

    Resolves the bundle to a concrete path via ``importlib.resources.as_file`` so
    it works zipped or from a source checkout, then copies it whole, skipping
    ``__pycache__``. The caller refuses to clobber first, so ``dest`` is fresh.
    """
    with as_file(files("daedalus") / "examples" / name) as concrete:
        shutil.copytree(concrete, dest, ignore=shutil.ignore_patterns("__pycache__"))
