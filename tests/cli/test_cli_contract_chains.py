"""One parametrized test over ``CONTRACT_CHAINS``.

Helpers and constants live in ``tests.cli._cli_contract``.
"""

from __future__ import annotations

import pytest

from tests.cli._cli_contract import CONTRACT_CHAINS, _reset_json_state, run_cli

pytestmark = pytest.mark.integration  # integration tier, CLI command chains

# Re-export the imported autouse fixture so ruff does not flag it as unused;
# pytest resolves it by name in this module's namespace.
__all__ = ["_reset_json_state"]


@pytest.mark.parametrize("argv, expected", CONTRACT_CHAINS)
def test_chain_resolves_its_declared_code_and_exit(
    argv: tuple[str, ...], expected: tuple[int, str]
) -> None:
    """Each chain resolves its declared outcome code and exit."""
    assert run_cli(*argv) == expected
