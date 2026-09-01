# /// script
# requires-python = ">=3.12"
# ///
"""The import-only probe run in a child interpreter for ``dae lab validate --deep``.

The parent (:func:`~daedalus.core.engine.subprocess_runner.probe_import`)
launches this script under a module's resolved env with the module directory on
argv. It loads ``main.py`` through the same ``load_entry`` scan as a real run, so
the module's top-level imports execute, but never calls the entry. A missing
third-party package is reported on stderr as ``DAE_MISSING_PACKAGE=<name>``, as
the run shim does; the exit code is 0 when the entry imports and 1 otherwise.
"""

from __future__ import annotations

import sys
from pathlib import Path

from daedalus.core.engine.step import StepError, load_entry

# The out-of-band marker the parent greps for to name a missing package; the
# same shape as the run shim's marker.
MISSING_PACKAGE_MARKER = "DAE_MISSING_PACKAGE="

_EXPECTED_ARGC = 1  # module_dir


def main(argv: list[str]) -> int:
    """Import one module's entry: 0 if it imports clean, 1 on a load failure."""
    if len(argv) != _EXPECTED_ARGC:
        sys.stderr.write("usage: _import_probe.py <module_dir>\n")
        return 2

    try:
        load_entry(Path(argv[0]) / "main.py")
    except StepError as error:
        if error.missing_package is not None:
            sys.stderr.write(MISSING_PACKAGE_MARKER + error.missing_package + "\n")
        sys.stderr.write(str(error) + "\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
