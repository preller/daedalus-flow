"""Shared helpers for the test_walks_* suites, not collected.

Fixture-lab roots, the inline-lab writer and the two propagate drivers.
"""

from __future__ import annotations

from pathlib import Path

from tests._helpers import examples_root, fixtures_root

_FIXTURE_LABS = fixtures_root() / "labs"
_DEMO_LAB = examples_root() / "demo"


def _make_lab(
    tmp_path: Path, modules: list[tuple[str, list[str], str]]
) -> tuple[object, Path]:
    """Write an inline lab (lab.yaml + per-module role files); return (spec, dir)."""
    from daedalus.core.recipe import load_recipe_text

    lab_dir = tmp_path / "lab"
    lines = ["name: inline", "modules:"]
    for module_id, depends, role in modules:
        lines.append(f"  - id: {module_id}")
        if depends:
            lines.append(f"    depends: [{', '.join(depends)}]")
        module_dir = lab_dir / "modules" / module_id
        module_dir.mkdir(parents=True)
        (module_dir / "dae-module.yaml").write_text(f"role: {role}\n")
    text = "\n".join(lines) + "\n"
    (lab_dir / "lab.yaml").write_text(text)
    return load_recipe_text(text), lab_dir


def _propagate_inline(
    tmp_path: Path, modules: list[tuple[str, list[str], str]]
) -> object:
    from daedalus.core.walks import propagate

    spec, lab_dir = _make_lab(tmp_path, modules)
    return propagate(spec, lab_dir)  # type: ignore[arg-type]


def _propagate_fixture(lab_dir: Path) -> object:
    from daedalus.core.recipe import load_recipe
    from daedalus.core.walks import propagate

    return propagate(load_recipe(lab_dir / "lab.yaml"), lab_dir)
