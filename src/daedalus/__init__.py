"""Design, validate and run labs of modules."""

from importlib.metadata import PackageNotFoundError, version

# The distribution name; must match [project].name in pyproject.toml.
_DIST_NAME = "daedalus-flow"

try:
    __version__ = version(_DIST_NAME)
except PackageNotFoundError:
    # Bare source tree (package not installed); keep imports working.
    __version__ = "0.0.0.dev0"
