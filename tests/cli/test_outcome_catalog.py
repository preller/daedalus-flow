"""The generated outcome-codes catalog stays in sync with the enum.

Regenerate with `uv run python scripts/gen_outcome_catalog.py` and review the diff.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# scripts/ is not a package and not on sys.path; add it so the generator imports here
# (mypy resolves it via mypy_path).
_SCRIPTS_DIR = str(Path(__file__).resolve().parents[2] / "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from gen_outcome_catalog import DOC_PATH, render_catalog  # noqa: E402


def test_outcome_catalog_doc_in_sync() -> None:
    rendered = render_catalog()
    if os.environ.get("UPDATE_OUTCOME_CATALOG"):
        DOC_PATH.write_text(rendered)
    assert DOC_PATH.exists(), (
        "docs/reference/outcome-codes.md missing; run scripts/gen_outcome_catalog.py"
    )
    assert DOC_PATH.read_text() == rendered, (
        "docs/reference/outcome-codes.md is stale vs the Outcome enum; regenerate with "
        "uv run python scripts/gen_outcome_catalog.py and review the diff"
    )
