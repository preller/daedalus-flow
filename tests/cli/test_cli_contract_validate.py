"""CLI contract tests for ``lab validate`` and ``lab visualize``.

Helpers, constants and fixtures live in ``tests.cli._cli_contract``.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from daedalus.cli.app import app
from tests._helpers import chdir, examples_root
from tests.cli._cli_contract import (
    _BROKEN_LABS,
    _WALK_VALIDATE_CODES,
    FAILURE_EXIT,
    OK_EXIT,
    _copy_fixture_lab,
    _reset_json_state,
    _run_cli_in,
    _visualize_payload,
    _visualize_payload_in,
    _write_inline_lab,
    run_cli,
)

pytestmark = pytest.mark.integration  # integration tier, CLI command chains

# Re-export imported fixtures so flake8/ruff do not flag them as unused; pytest
# resolves them by name in this module's namespace.
__all__ = ["_reset_json_state"]


def test_lab_visualize_orders_by_toposort_with_layers_byte_stable() -> None:
    """The expected order and layers are recomputed from the topology, not frozen."""
    import networkx as nx

    from daedalus.core import topology

    graph = nx.DiGraph()
    graph.add_nodes_from(node for node, _ in topology.NODES)
    graph.add_edges_from(topology.EDGES)
    expected_order = list(nx.lexicographical_topological_sort(graph, key=str))
    # topological_generations yields unordered sets, so each generation is sorted
    # by id; a list(gen) in the implementation would leak set order into a layer.
    generations = [sorted(gen) for gen in nx.topological_generations(graph)]
    expected_layer = {
        node: index for index, gen in enumerate(generations) for node in gen
    }

    payload = _visualize_payload()
    nodes = payload["topology"]["nodes"]

    # nodes are in lexicographical_topological_sort order.
    assert [n["id"] for n in nodes] == expected_order
    # nodes grouped by layer equal the sorted generations.
    grouped: dict[int, list[str]] = {}
    for node in nodes:
        grouped.setdefault(node["layer"], []).append(node["id"])
    assert grouped == dict(enumerate(generations))
    # each node carries its sorted-generation layer index.
    assert {n["id"]: n["layer"] for n in nodes} == expected_layer
    # the source is layer 0; the sink is the last layer.
    assert nodes[0]["layer"] == 0
    assert nodes[-1]["id"] == topology.sink()

    # byte-stable across two invocations.
    assert json.dumps(_visualize_payload(), sort_keys=True) == json.dumps(
        payload, sort_keys=True
    )

    # no fan-out count anywhere in the payload; the view is static.
    flat = json.dumps(payload)
    assert "fan_out" not in flat
    assert "fanout" not in flat
    assert all("count" not in node for node in nodes)


def test_lab_validate_parse_error_on_unparseable(tmp_path: Path) -> None:
    """validate reports a broken file as failure (exit 1); run refuses it (exit 2)."""
    target = tmp_path / "unparseable.yaml"
    shutil.copyfile(_BROKEN_LABS / "unparseable.yaml", target)
    assert _run_cli_in(tmp_path, "lab", "validate", str(target)) == (
        FAILURE_EXIT,
        "dae.lab.validate.parse_error",
    )


# Bare `lab validate` and `lab visualize` operate on the cwd lab, as `lab run`
# does; the exemplar is the fallback for a cwd with no lab.yaml.


def test_lab_validate_no_path_catches_broken_cwd_lab(tmp_path: Path) -> None:
    """A broken ./lab.yaml in cwd reports its defect (exit 1), not the exemplar's ok."""
    lab = tmp_path / "walk_collector_solo"
    shutil.copytree(
        _BROKEN_LABS / "walk_collector_solo",
        lab,
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    assert _run_cli_in(lab, "lab", "validate") == (
        FAILURE_EXIT,
        "dae.lab.validate.walk_collector_solo",
    )


def test_lab_validate_no_path_ok_on_sound_cwd_lab(tmp_path: Path) -> None:
    """Bare `lab validate` on a sound cwd lab validates that lab (ok)."""
    lab = _copy_fixture_lab("linear_smoke", tmp_path)
    assert _run_cli_in(lab, "lab", "validate") == (OK_EXIT, "dae.lab.validate.ok")


def test_lab_validate_no_path_falls_back_to_exemplar_when_no_cwd_lab() -> None:
    """``run_cli`` runs in an empty cwd, so the exemplar fallback reports ok."""
    assert run_cli("lab", "validate") == (OK_EXIT, "dae.lab.validate.ok")


def test_lab_visualize_no_path_renders_cwd_lab(tmp_path: Path) -> None:
    """The payload lists linear_smoke's modules, not the exo-survey exemplar's."""
    lab = _copy_fixture_lab("linear_smoke", tmp_path)
    runner = CliRunner()
    with chdir(lab):
        result = runner.invoke(app, ["--json", "lab", "visualize"], prog_name="dae")
    assert result.exit_code == OK_EXIT
    payload = json.loads(result.stdout)["data"]  # the envelope nests it under data
    nodes = payload["topology"]["nodes"]
    ids = [n["id"] for n in nodes]
    assert "emit_ticks" in ids  # linear_smoke's source
    assert (
        "emit_targets" not in ids
    )  # emit_targets is the exemplar's source, absent here
    # nodes carry real roles and toposort layers; the static view has no counts
    assert all("role" in n and "layer" in n for n in nodes)
    assert all("count" not in n and "fan_out" not in n for n in nodes)


def test_lab_visualize_no_path_refuses_broken_cwd_lab(tmp_path: Path) -> None:
    """An unparseable cwd lab gives parse_error (exit 1), not the exemplar's ok."""
    shutil.copyfile(_BROKEN_LABS / "unparseable.yaml", tmp_path / "lab.yaml")
    assert _run_cli_in(tmp_path, "lab", "visualize") == (
        FAILURE_EXIT,
        "dae.lab.validate.parse_error",
    )


def test_lab_visualize_no_path_exemplar_fallback_when_no_cwd_lab() -> None:
    """``_visualize_payload`` runs in an empty cwd, so the exemplar appears."""
    payload = _visualize_payload()
    ids = [n["id"] for n in payload["topology"]["nodes"]]
    assert "emit_targets" in ids


def test_lab_visualize_one_key_set_for_one_outcome_code(tmp_path: Path) -> None:
    """The exemplar branch carries the walk keys as null rather than absent."""
    exemplar = _visualize_payload()  # no cwd lab -> exemplar branch
    lab = _copy_fixture_lab("diamond_join", tmp_path)
    cwd = _visualize_payload_in(lab)  # real cwd lab -> walk-census branch

    expected = {"topology", "walks", "walk_lines", "token_walk_lines"}
    assert set(exemplar) == expected, set(exemplar)
    assert set(cwd) == expected, set(cwd)
    # the exemplar computes no census, so its walk keys are null.
    assert exemplar["walks"] is None
    assert exemplar["walk_lines"] is None
    assert exemplar["token_walk_lines"] is None
    # the real cwd lab fills them with the computed census.
    assert cwd["walks"] is not None
    assert cwd["walk_lines"] is not None


@pytest.mark.parametrize("code_string", _WALK_VALIDATE_CODES)
def test_walk_validate_outcome_members_exist(code_string: str) -> None:
    """Each walk-model validate code is a FAILURE member of Outcome with exit 1."""
    from daedalus.core.outcomes import Category, Outcome

    # Find the member by its code string value (the enum is a StrEnum).
    # cast() would also work; _value2member_map_ is the typed internal dict.
    member: Outcome = Outcome._value2member_map_[code_string]  # type: ignore[assignment]
    assert member.category == Category.FAILURE, (
        f"{code_string}: expected Category.FAILURE, got {member.category}"
    )
    assert member.exit_code == 1, (
        f"{code_string}: expected exit_code 1, got {member.exit_code}"
    )


def test_validate_wires_branch_then_collect_as_walk_sound(tmp_path: Path) -> None:
    """The solo pre-pass defers to the token pass, which finds the collector legal."""
    lab_dir = tmp_path / "branch_then_collect"
    _write_inline_lab(
        lab_dir,
        [
            ("seed", "transform", []),
            ("left", "transform", ["seed"]),
            ("right", "transform", ["seed"]),
            ("d", "transform", ["left", "right"]),
            ("join", "walk_collector", ["d"]),
        ],
    )
    assert _run_cli_in(tmp_path, "lab", "validate", str(lab_dir / "lab.yaml")) == (
        OK_EXIT,
        "dae.lab.validate.ok",
    )


def test_validate_wires_emitter_multi_successor(tmp_path: Path) -> None:
    """An emitter with two successors -> dae.lab.validate.emitter_multi_successor."""
    lab_dir = tmp_path / "emitter_fanout"
    _write_inline_lab(
        lab_dir,
        [
            ("src", "emitter", []),
            ("a", "transform", ["src"]),
            ("b", "transform", ["src"]),
        ],
    )
    assert _run_cli_in(tmp_path, "lab", "validate", str(lab_dir / "lab.yaml")) == (
        FAILURE_EXIT,
        "dae.lab.validate.emitter_multi_successor",
    )


def test_validate_wires_reserved_separator_in_id(tmp_path: Path) -> None:
    """A module id containing `@` -> dae.lab.validate.reserved_separator_in_id."""
    lab_dir = tmp_path / "reserved_sep"
    _write_inline_lab(
        lab_dir,
        [
            ("src", "transform", []),
            ("fit@home", "transform", ["src"]),
        ],
    )
    assert _run_cli_in(tmp_path, "lab", "validate", str(lab_dir / "lab.yaml")) == (
        FAILURE_EXIT,
        "dae.lab.validate.reserved_separator_in_id",
    )


def test_first_defect_only_order_with_walk_defects(tmp_path: Path) -> None:
    """The reserved separator wins over a collector defect; a cycle wins over both."""
    # Reserved separator wins over a (would-be) incomplete-group collector.
    both = tmp_path / "sep_and_group"
    _write_inline_lab(
        both,
        [
            ("seed", "transform", []),
            ("left", "transform", ["seed"]),
            ("right", "transform", ["seed"]),
            # a `@` module id and a partial-group collector over the left branch
            # only; the separator wins.
            ("c@t", "walk_collector", ["left"]),
        ],
    )
    assert _run_cli_in(both, "lab", "validate", str(both / "lab.yaml")) == (
        FAILURE_EXIT,
        "dae.lab.validate.reserved_separator_in_id",
    )

    # A cyclic lab reports the cycle even with a walk_collector present, since
    # first_defect runs before the walk pass.
    cyclic = tmp_path / "cyclic_walk"
    _write_inline_lab(
        cyclic,
        [
            ("a", "transform", ["c"]),
            ("b", "transform", ["a"]),
            ("c", "walk_collector", ["b"]),
        ],
    )
    assert _run_cli_in(cyclic, "lab", "validate", str(cyclic / "lab.yaml")) == (
        FAILURE_EXIT,
        "dae.lab.validate.cycle",
    )


def test_visualize_payload_walks_diamond_join(tmp_path: Path) -> None:
    """Each walk record carries the five fields plus user_walk, null on the root."""
    lab = _copy_fixture_lab("diamond_join", tmp_path)
    payload = _visualize_payload_in(lab)

    # walk_lines is the user-facing configuration view.
    assert payload["walk_lines"] == [
        "Full:  1-{2,3}-(4)",
        "Walks: 2",
        "  walk_1: 1-2-(4)",
        "  walk_2: 1-3-(4)",
    ]
    # token_walk_lines is the internal token-set run-once view (machine only).
    assert payload["token_walk_lines"] == [
        "Full:  1-(2,3)-4",
        "Walks: 2",
        "  walk_1: 1-2-(4)",
        "  walk_2: 1-3-(4)",
    ]

    walks = payload["walks"]
    assert [w["walk_id"] for w in walks] == ["w1", "w2", "w3"]
    # every record exposes the full 5-field shape plus the user_walk bridge.
    for record in walks:
        assert set(record) == {
            "walk_id",
            "flight_id",
            "parent_walk",
            "born_at",
            "branch_module",
            "user_walk",
        }
    # the user_walk equals the on-disk walk_J dir name (branch walks only).
    by_id = {w["walk_id"]: w for w in walks}
    assert by_id["w1"]["user_walk"] is None
    assert by_id["w2"]["user_walk"] == "walk_1"
    assert by_id["w3"]["user_walk"] == "walk_2"

    # byte-stable across two invocations.
    again = _visualize_payload_in(lab)
    assert json.dumps(again, sort_keys=True) == json.dumps(payload, sort_keys=True)


def test_visualize_static_hides_flights(tmp_path: Path) -> None:
    """N is unknown until the generator runs, so the static block has no flights."""
    demo = tmp_path / "demo"
    shutil.copytree(
        examples_root() / "demo", demo, ignore=shutil.ignore_patterns("__pycache__")
    )
    block = "\n".join(_visualize_payload_in(demo)["walk_lines"])
    assert "<f1>" not in block
    assert "f1 = " not in block
    assert "flight_" not in block


def test_visualize_payload_walks_demo_m1(tmp_path: Path) -> None:
    """Successors sort fit_mcmc before fit_nested; the block is ASCII only."""
    demo = tmp_path / "demo"
    shutil.copytree(
        examples_root() / "demo", demo, ignore=shutil.ignore_patterns("__pycache__")
    )
    payload = _visualize_payload_in(demo)

    assert payload["walk_lines"] == [
        "Full:  1-2-{3,4}-(5)-[6]",
        "Walks: 2",
        "  walk_1: 1-2-3-(5)-[6]",
        "  walk_2: 1-2-4-(5)-[6]",
    ]
    assert payload["token_walk_lines"] == [
        "Full:  1-2-(3,4)-5-6",
        "Walks: 2",
        "  walk_1: 1-2-3-(5)-6",
        "  walk_2: 1-2-4-(5)-6",
    ]
    assert all(line.isascii() for line in payload["walk_lines"])
    assert {w["walk_id"] for w in payload["walks"]} == {"w1", "w2", "w3", "w4"}
    user = {w["walk_id"]: w["user_walk"] for w in payload["walks"]}
    assert user == {"w1": None, "w2": None, "w3": "walk_1", "w4": "walk_2"}


def test_visualize_defective_walk_lab_surfaces_validate_verdict(
    tmp_path: Path,
) -> None:
    """A collector over 2 of 3 siblings gives collector_incomplete_group (exit 1)."""
    lab = tmp_path / "incomplete_group"
    _write_inline_lab(
        lab,
        [
            ("src", "transform", []),
            ("b_a", "transform", ["src"]),
            ("b_b", "transform", ["src"]),
            ("b_c", "transform", ["src"]),
            ("join", "walk_collector", ["b_a", "b_b"]),
        ],
    )
    assert _run_cli_in(lab, "lab", "visualize") == (
        FAILURE_EXIT,
        "dae.lab.validate.collector_incomplete_group",
    )
