"""The child import root exposes ``daedalus`` and nothing else, in any layout.

A src checkout qualifies as-is; an installed site-packages is staged into the cache.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path

import pytest

from daedalus.core.engine import subprocess_runner

_MTIME_BUMP_NS = 2_000_000_000  # 2s: safely past any filesystem's mtime granularity
_RACERS = 8


def _fake_package(root: Path, name: str = "daedalus") -> Path:
    """A minimal importable package dir under *root*."""
    pkg = root / name
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    return pkg


def test_src_layout_qualifies(tmp_path: Path) -> None:
    """Asserted on a tmp replica, since the live src/ may hold a stray .DS_Store."""
    src = tmp_path / "src"
    _fake_package(src)
    assert subprocess_runner._exposes_only_daedalus(src)


def test_bytecode_cache_does_not_disqualify(tmp_path: Path) -> None:
    """A stray ``__pycache__`` beside the package is ignored, not disqualifying."""
    _fake_package(tmp_path)
    (tmp_path / "__pycache__").mkdir()
    assert subprocess_runner._exposes_only_daedalus(tmp_path)


def test_site_packages_layout_is_rejected(tmp_path: Path) -> None:
    """numpy stands for any parent library that would shadow the module's own pin."""
    _fake_package(tmp_path)
    _fake_package(tmp_path, "numpy")
    _fake_package(tmp_path, "typer")
    assert not subprocess_runner._exposes_only_daedalus(tmp_path)


def test_missing_dir_is_rejected(tmp_path: Path) -> None:
    """An unreadable or absent candidate is disqualified, never assumed usable."""
    assert not subprocess_runner._exposes_only_daedalus(tmp_path / "nope")


def test_staged_root_exposes_only_daedalus(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Staging a mixed layout yields a single-entry root pointing at the package."""
    site_packages = tmp_path / "site-packages"
    package = _fake_package(site_packages)
    _fake_package(site_packages, "numpy")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))

    root = subprocess_runner._staged_import_root(package)

    assert subprocess_runner._exposes_only_daedalus(root)
    staged = root / "daedalus"
    assert (staged / "__init__.py").exists()
    # resolve() equality holds only on the symlink branch; the copy fallback is
    # pinned by test_staged_root_copy_fallback_serves_current_code.
    if staged.is_symlink():
        assert staged.resolve() == package.resolve()
    # The cache lives under `XDG_CACHE_HOME`, not inside the install.
    assert str(root).startswith(str(tmp_path / "cache"))


def test_staging_is_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Re-staging the same install returns the same root without rebuilding it."""
    package = _fake_package(tmp_path / "site-packages")
    _fake_package(tmp_path / "site-packages", "numpy")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))

    first = subprocess_runner._staged_import_root(package)
    second = subprocess_runner._staged_import_root(package)

    assert first == second
    assert subprocess_runner._exposes_only_daedalus(second)


def test_import_root_stages_when_the_parent_layout_is_mixed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A wheel install is staged, never handed over as site-packages."""
    site_packages = tmp_path / "lib" / "python3.12" / "site-packages"
    package = _fake_package(site_packages)
    _fake_package(site_packages, "rich")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setattr(subprocess_runner, "_PACKAGE_DIR", package)

    root = subprocess_runner._daedalus_import_root()

    assert root != site_packages, "site-packages must not be used as an import root"
    assert root.is_dir()
    assert subprocess_runner._exposes_only_daedalus(root)
    assert (root / "daedalus" / "__init__.py").exists()


def test_import_root_uses_a_single_package_parent_directly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A src layout is used as-is, with no staging and no cache entry."""
    src = tmp_path / "src"
    package = _fake_package(src)
    cache = tmp_path / "cache"
    monkeypatch.setenv("XDG_CACHE_HOME", str(cache))
    monkeypatch.setattr(subprocess_runner, "_PACKAGE_DIR", package)

    assert subprocess_runner._daedalus_import_root() == src
    assert not cache.exists(), "a qualifying layout must not touch the cache"


def test_staged_root_copy_fallback_serves_current_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The copy fallback re-stages when the install changes at the same version."""
    package = _fake_package(tmp_path / "site-packages")
    _fake_package(tmp_path / "site-packages", "numpy")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setattr(
        Path, "symlink_to", lambda *a, **kw: (_ for _ in ()).throw(OSError("nope"))
    )

    first = subprocess_runner._staged_import_root(package)
    assert not (first / "daedalus").is_symlink(), "the fallback must be a real copy"
    assert subprocess_runner._exposes_only_daedalus(first)
    assert (first / "daedalus" / "__init__.py").read_text() == ""

    # A same-version rebuild, with new content and an mtime bumped past fs granularity.
    marker = "REBUILT = True\n"
    (package / "__init__.py").write_text(marker)
    stat = (package / "__init__.py").stat()
    os.utime(
        package / "__init__.py",
        ns=(stat.st_atime_ns, stat.st_mtime_ns + _MTIME_BUMP_NS),
    )

    second = subprocess_runner._staged_import_root(package)
    assert second != first, "a changed install must land in a fresh cache entry"
    assert (second / "daedalus" / "__init__.py").read_text() == marker


def test_staging_race_is_safe(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Racing resolvers on a cold cache all get one valid root; none raises."""
    package = _fake_package(tmp_path / "site-packages")
    _fake_package(tmp_path / "site-packages", "numpy")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))

    barrier = threading.Barrier(_RACERS)
    roots: list[Path] = []
    errors: list[BaseException] = []

    def resolve() -> None:
        barrier.wait()
        try:
            roots.append(subprocess_runner._staged_import_root(package))
        except BaseException as error:  # noqa: BLE001 (the test collects any crash)
            errors.append(error)

    threads = [threading.Thread(target=resolve) for _ in range(_RACERS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors, f"racing resolvers must not crash: {errors!r}"
    assert len(set(roots)) == 1, "every racer must resolve the same root"
    assert subprocess_runner._exposes_only_daedalus(roots[0])
    assert (roots[0] / "daedalus" / "__init__.py").exists()


def test_unwritable_cache_raises_subprocess_step_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unstageable cache raises SubprocessStepError, not a raw traceback."""
    package = _fake_package(tmp_path / "site-packages")
    _fake_package(tmp_path / "site-packages", "numpy")
    not_a_dir = tmp_path / "cachefile"
    not_a_dir.write_text("")
    monkeypatch.setenv("XDG_CACHE_HOME", str(not_a_dir))

    with pytest.raises(subprocess_runner.SubprocessStepError, match="cannot stage"):
        subprocess_runner._staged_import_root(package)


def test_empty_dir_is_not_an_import_root(tmp_path: Path) -> None:
    """An empty dir, or one with only __pycache__, does not qualify."""
    empty = tmp_path / "empty"
    empty.mkdir()
    assert not subprocess_runner._exposes_only_daedalus(empty)
    (empty / "__pycache__").mkdir()
    assert not subprocess_runner._exposes_only_daedalus(empty)


def test_package_dir_is_layout_independent() -> None:
    """The walk to the package dir never steps outside the package."""
    assert subprocess_runner._PACKAGE_DIR.name == "daedalus"
    assert (subprocess_runner._PACKAGE_DIR / "core" / "engine").is_dir()
    assert subprocess_runner._PACKAGE_NAME == "daedalus"
