"""Generate ``docs/reference/outcome-codes.md`` from the Outcome registry.

The ``--json`` ``code`` field is the machine contract and this catalog is its
published form. The file is generated, never hand-edited, and
``tests/cli/test_outcome_catalog.py`` fails when it drifts from the enum.

Regenerate with ``uv run python scripts/gen_outcome_catalog.py``.
"""

from __future__ import annotations

from pathlib import Path

from daedalus.core.outcomes import Outcome

DOC_PATH = (
    Path(__file__).resolve().parents[1] / "docs" / "reference" / "outcome-codes.md"
)


def render_catalog() -> str:
    """Render the whole Outcome registry as a deterministic markdown table."""
    lines: list[str] = [
        "# Outcome codes",
        "",
        "Generated from `daedalus.core.outcomes` by",
        "`scripts/gen_outcome_catalog.py`. Do not edit by hand: change the codes and",
        "regenerate. Each code is the stable `--json` `code` value; `exit` is the",
        "process exit status the category carries.",
        "",
        "| code | category | exit |",
        "| --- | --- | --- |",
    ]
    for outcome in sorted(Outcome, key=str):
        lines.append(f"| `{outcome}` | {outcome.category.name} | {outcome.exit_code} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    """Write the catalog to ``docs/reference/outcome-codes.md``."""
    DOC_PATH.write_text(render_catalog())
    print(f"wrote {DOC_PATH} ({len(list(Outcome))} codes)")


if __name__ == "__main__":
    main()
