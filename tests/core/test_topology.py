"""The reserved dir-name constants and the pure path builders for the run tree.

Names are defined once in topology.py; the builders return strings only.
"""

from daedalus.core import topology


def test_reserved_dir_name_constants() -> None:
    """The nested-tree reserved dir names exist with exact string values."""
    assert topology.FLIGHTS_DIR == "flights"
    assert topology.WALKS_DIR == "walks"
    assert topology.WALK_DIR_PREFIX == "walk_"
    assert topology.FLIGHT_DIR_PREFIX == "flight_"
    assert topology.FINAL_DIR == "final"


def test_flight_dir_builder() -> None:
    """``flight_dir`` nests a flight under ``flights/`` with the walk_J... reset."""
    assert (
        topology.flight_dir("flow_x", 1) == "dae-outputs/flows/flow_x/flights/flight_1/"
    )
    assert (
        topology.flight_dir("flow_x", 2) == "dae-outputs/flows/flow_x/flights/flight_2/"
    )


def test_walk_dir_builder() -> None:
    """``walk_dir`` nests a walk under its flight's ``walks/`` sublevel."""
    assert (
        topology.walk_dir("flow_x", 1, 1)
        == "dae-outputs/flows/flow_x/flights/flight_1/walks/walk_1/"
    )
    assert (
        topology.walk_dir("flow_x", 1, 2)
        == "dae-outputs/flows/flow_x/flights/flight_1/walks/walk_2/"
    )


def test_flight_final_dir_builder() -> None:
    """``flight_final_dir`` is the per-flight ``final/`` (the walk-collector tail)."""
    assert (
        topology.flight_final_dir("flow_x", 1)
        == "dae-outputs/flows/flow_x/flights/flight_1/final/"
    )


def test_flow_final_dir_builder() -> None:
    """``flow_final_dir`` is the flow-level ``final/`` (the sink result)."""
    assert topology.flow_final_dir("flow_x") == "dae-outputs/flows/flow_x/final/"
