# Quality gate for daedalus. CI and pre-commit call these recipes, so the gate is defined once.
# `just` is a system binary (nixpkgs or cargo), not a Python dep; run it from this directory.

# The active venv; `UV_PROJECT_ENVIRONMENT` wins when set, otherwise the in-tree .venv.
venv := env_var_or_default("UV_PROJECT_ENVIRONMENT", ".venv")

# The blocking gate is the default recipe.
default: gate

# ruff check and format drift over src and tests, the same scope as the pre-commit hooks.
lint:
    uv run ruff check src tests
    uv run ruff format --check src tests

# Strict type check; the mypy config lives in pyproject.toml.
typecheck:
    uv run mypy

# Import-layer contracts (import-linter).
imports:
    uv run lint-imports

# The fast suite, everything but the real samplers, under the coverage floor from pyproject.
test:
    uv run pytest -m "not slow" --cov=daedalus --cov-branch --cov-report=term-missing

# The real-sampler suite (dynesty, emcee, scipy), then the tutorial notebooks under nbmake.
test-slow:
    uv run pytest -m slow
    uv run pytest --nbmake src/daedalus/examples/minimal/tutorial.ipynb src/daedalus/examples/demo/tutorial.ipynb

# The Nix-only isolation tests (uv2nix per-module build); they skip on a host that cannot build.
test-nix:
    uv run pytest tests/core/engine/test_isolation_nix.py tests/core/engine/test_isolation_nix_example.py tests/core/engine/test_isolation_nix_science.py

# The unit tier only, the untagged default pool, without the coverage gate.
test-unit:
    uv run pytest -m "not slow and not e2e and not integration"

# The integration tier, engine, scheduler and isolation across modules plus the CLI contract.
test-integration:
    uv run pytest -m "integration"

# pip-audit of the locked default closure (network); CVE-2025-71176 (pytest tmp dir, dev-only) stays ignored until pytest 9.
audit:
    uv export --locked --no-emit-project --quiet | uv run pip-audit --no-deps --ignore-vuln CVE-2025-71176 -r /dev/stdin

# The blocking sequence.
gate: lint typecheck imports test audit

# Local mirror of the blocking CI jobs (lint, typecheck, test) with each job's sync state; see ci-local-313.
ci-local:
    uv sync --locked
    just lint
    just imports
    uv sync --locked --all-groups
    just typecheck
    {{venv}}/bin/python -m pytest -m "not slow" --cov=daedalus --cov-branch --cov-report=term-missing

# The 3.13 leg of the CI test matrix; uv fetches 3.13 if absent, and the last line restores the 3.12 venv.
ci-local-313:
    uv sync --locked --all-groups -p 3.13
    {{venv}}/bin/python -m pytest -m "not slow" --cov=daedalus --cov-branch --cov-report=term-missing
    uv sync --locked --all-groups

# Build the docs site under -W, as Read the Docs does. Output lands in docs/_build/html.
docs:
    uv run --locked --group docs sphinx-build -W -b html docs docs/_build/html

# Cross-reference link check, run apart from `docs`.
docs-linkcheck:
    uv run --locked --group docs sphinx-build -b linkcheck docs docs/_build/linkcheck

# Build the site, then serve it at http://localhost:8000.
docs-serve: docs
    uv run python -m http.server 8000 --directory docs/_build/html
