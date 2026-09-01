"""The ensemble emit module skips blank and # lines in a commented targets.csv.

Without the skip, csv.DictReader takes the first # line as the field names.
"""

import json
from pathlib import Path

import daedalus.flow as dae
from tests._helpers import examples_root, load_entry, run_module

EMIT = examples_root() / "ensemble" / "modules" / "emit" / "main.py"


def _emit(input_dir: Path, out_dir: Path) -> list[dict[str, object]]:
    out = run_module(
        load_entry(EMIT),
        role=dae.Role.EMITTER,
        output_dir=out_dir,
        input_dir=input_dir,
    )
    return json.loads((out / "roster.json").read_text())


def test_emit_skips_commented_and_blank_lines(tmp_path: Path) -> None:
    """A documented header plus a blank line yields exactly the data rows."""
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "targets.csv").write_text(
        "# ensemble targets, one row per star.\n"
        "# name = identifier; value = transit signal-to-noise\n"
        "\n"
        "name,value,period_days\n"
        "WASP-12 b,38.4,1.0914203\n"
        "GJ 1214 b,18.4,1.5804040\n"
    )
    roster = _emit(input_dir, tmp_path / "out")
    assert [r["name"] for r in roster] == ["WASP-12 b", "GJ 1214 b"]
    assert roster[0]["value"] == 38.4  # noqa: PLR2004 (the literal is the contract)
    assert all(set(r) == {"name", "value"} for r in roster)


def test_emit_parses_the_shipped_commented_targets_csv(tmp_path: Path) -> None:
    """The shipped targets.csv with its commented header yields 4 targets."""
    shipped = examples_root() / "ensemble" / "input"
    roster = _emit(shipped, tmp_path / "out")
    assert [r["name"] for r in roster] == [
        "WASP-12 b",
        "HD 209458 b",
        "GJ 1214 b",
        "TRAPPIST-1 e",
    ]


def test_emit_refuses_an_all_comment_file(tmp_path: Path) -> None:
    """An all-comment file has no header; emit writes an empty roster."""
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "targets.csv").write_text("# only comments here\n# no header\n")
    roster = _emit(input_dir, tmp_path / "out")
    assert roster == []
