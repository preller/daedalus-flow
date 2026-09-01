"""The visualize payload tags each node with an additive ``flight_scoped`` bool.

A module is flight scoped when it sits between an emitter and a flight_collector.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.cli._cli_contract import (
    _copy_fixture_lab,
    _reset_json_state,
    _visualize_payload,
    _visualize_payload_in,
)

pytestmark = pytest.mark.integration  # integration tier, CLI surface contract

# Re-export the autouse fixture so ruff does not flag the import as unused; pytest
# resolves it by name in this module's namespace.
__all__ = ["_reset_json_state"]


# The exemplar topology (src/daedalus/core/topology.py): emit_targets ->
# fetch_data -> {fit_nested, fit_mcmc} -> compare_methods -> summarize_population.
# The per-flight band is everything strictly between the emitter and collector.
_EXEMPLAR_SCOPED = {"fetch_data", "fit_nested", "fit_mcmc", "compare_methods"}
_EXEMPLAR_UNSCOPED = {"emit_targets", "summarize_population"}

# linear_smoke fixture: emit_ticks(emitter) -> debug_io -> sleep_briefly ->
# summarize_walk -> collect_report(flight_collector). The three transforms are
# the per-flight band; the boundary emitter and flight_collector are not.
_LINEAR_SCOPED = {"debug_io", "sleep_briefly", "summarize_walk"}
_LINEAR_UNSCOPED = {"emit_ticks", "collect_report"}


def _scope_map(payload: dict) -> dict[str, bool]:
    """Node id to flight_scoped; asserts every node carries the key as a bool."""
    nodes = payload["topology"]["nodes"]
    for node in nodes:
        assert "flight_scoped" in node, f"node missing flight_scoped: {node}"
        assert isinstance(node["flight_scoped"], bool), node
    return {node["id"]: node["flight_scoped"] for node in nodes}


def test_exemplar_payload_tags_flight_band() -> None:
    """The no-lab exemplar payload tags the per-flight band; boundaries are false."""
    scope = _scope_map(_visualize_payload())
    assert {mod for mod, flag in scope.items() if flag} == _EXEMPLAR_SCOPED, scope
    assert all(not scope[mod] for mod in _EXEMPLAR_UNSCOPED), scope


def test_cwd_lab_payload_tags_flight_band(tmp_path: Path) -> None:
    """On linear_smoke the three transforms are scoped; the boundaries are not."""
    lab_dir = _copy_fixture_lab("linear_smoke", tmp_path)
    scope = _scope_map(_visualize_payload_in(lab_dir))
    assert {mod for mod, flag in scope.items() if flag} == _LINEAR_SCOPED, scope
    assert all(not scope[mod] for mod in _LINEAR_UNSCOPED), scope


def test_flight_band_empty_without_a_boundary_role() -> None:
    """Only the helper reaches this; a collector-less lab does not visualize ok."""
    import networkx as nx

    from daedalus.cli.render._topology import _flight_scoped_nodes
    from daedalus.flow import Role

    no_collector = nx.DiGraph()
    no_collector.add_node("e", role=Role.EMITTER)
    no_collector.add_node("t", role=Role.TRANSFORM)
    no_collector.add_edge("e", "t")
    assert (
        _flight_scoped_nodes(no_collector, lambda n: no_collector.nodes[n]["role"])
        == frozenset()
    )

    no_emitter = nx.DiGraph()
    no_emitter.add_node("t", role=Role.TRANSFORM)
    no_emitter.add_node("c", role=Role.FLIGHT_COLLECTOR)
    no_emitter.add_edge("t", "c")
    assert (
        _flight_scoped_nodes(no_emitter, lambda n: no_emitter.nodes[n]["role"])
        == frozenset()
    )
