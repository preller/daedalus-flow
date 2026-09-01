"""daedalus.cli - the command-line interface.

Builds the ``dae`` / ``daedalus`` console scripts (both point at :func:`main`).
This is not a public Python API; script authors should use :mod:`daedalus.flow`.
"""

from daedalus.cli.app import app, main

__all__ = ["app", "main"]
