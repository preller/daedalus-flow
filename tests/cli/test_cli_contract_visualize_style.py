"""``dae lab visualize --style`` routes to the right human render.

Expected ids come from the visualize payload; graph styles need the ``viz`` extra.
"""

from __future__ import annotations

import importlib.util
import json

import pytest
from typer.testing import CliRunner

from daedalus.cli.app import app
from tests.cli._cli_contract import (
    OK_EXIT,
    _human_stdout,
    _isolated_cwd,
    _reset_json_state,
    _visualize_payload,
    runner,
)

pytestmark = pytest.mark.integration  # integration tier, CLI surface contract

# Re-export the imported fixtures so ruff does not flag them as unused; pytest
# resolves them by name in this module's namespace.
__all__ = ["_reset_json_state", "runner"]

# The graph styles need the optional `viz` extra (grandalf). Skip when it is
# absent rather than fail; CI installs it, and the absent-extra path is pinned
# by test_missing_viz_extra_*.
_HAS_VIZ = importlib.util.find_spec("grandalf") is not None
_GRAPH_STYLES = ["full", "num", "rolenum"]


def _exemplar_ids() -> set[str]:
    """Every module id in the no-lab exemplar visualize payload."""
    return {node["id"] for node in _visualize_payload()["topology"]["nodes"]}


@pytest.mark.skipif(not _HAS_VIZ, reason="graph styles need the viz extra (grandalf)")
@pytest.mark.parametrize("style", _GRAPH_STYLES)
def test_graph_style_renders_every_id_and_role_glyph(
    runner: CliRunner, style: str
) -> None:
    """Module ids are lowercase, so an uppercase E/T/W/F is a role glyph."""
    ids = _exemplar_ids()
    with _isolated_cwd():
        text = _human_stdout(runner, ["lab", "visualize", "--style", style])
    missing = sorted(mod for mod in ids if mod not in text)
    assert not missing, f"--style {style} omitted ids {missing}\n{text}"
    for glyph in "ETWF":
        assert glyph in text, f"--style {style} missing role glyph {glyph!r}\n{text}"


@pytest.mark.skipif(not _HAS_VIZ, reason="graph styles need the viz extra (grandalf)")
def test_full_style_shows_the_role_legend(runner: CliRunner) -> None:
    """`--style full` prints the role legend so the bare glyphs are decodable."""
    with _isolated_cwd():
        text = _human_stdout(runner, ["lab", "visualize", "--style", "full"])
    for word in ("emitter", "transform", "walk-collector", "flight-collector"):
        assert word in text, f"role legend missing {word!r}\n{text}"


def test_default_style_is_the_table(runner: CliRunner) -> None:
    """No `--style` keeps the familiar topology table, not a graph (back-compat)."""
    with _isolated_cwd():
        text = _human_stdout(runner, ["lab", "visualize"])
    assert "feeds-into" in text, f"default view is not the table\n{text}"
    assert "+--" not in text, f"default view drew a graph box\n{text}"


@pytest.mark.skipif(not _HAS_VIZ, reason="graph styles need the viz extra (grandalf)")
@pytest.mark.parametrize("style", _GRAPH_STYLES)
def test_json_visualize_style_carries_no_ansi(style: str) -> None:
    """Under --json the command builds no Text, so stdout is the plain envelope."""
    cli_runner = CliRunner()
    with _isolated_cwd():
        result = cli_runner.invoke(
            app, ["--json", "lab", "visualize", "--style", style], prog_name="dae"
        )
    assert result.exit_code == OK_EXIT, result.stdout
    assert "\x1b[" not in result.stdout, (
        f"ANSI escape in --json stdout:\n{result.stdout!r}"
    )
    data = json.loads(result.stdout)
    assert data["code"] == "dae.lab.visualize.ok"
    assert "\x1b[" not in json.dumps(data)


def test_missing_viz_extra_prints_install_hint_and_stays_ok(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GraphLayoutUnavailable becomes a stderr hint; the outcome stays ok."""
    import daedalus.cli.render as render_pkg
    from daedalus.cli.console import err

    def _no_grandalf(*args: object, **kwargs: object) -> None:
        raise render_pkg.GraphLayoutUnavailable(
            "graph views need the optional 'viz' extra (the grandalf layout "
            "engine); install it with: pip install daedalus-flow[viz]"
        )

    monkeypatch.setattr(render_pkg, "lab_visualize_graph", _no_grandalf)
    with _isolated_cwd(), err.capture() as hint:
        result = runner.invoke(
            app, ["lab", "visualize", "--style", "full"], prog_name="dae"
        )
    assert result.exit_code == OK_EXIT, result.output
    assert result.exception is None, result.exception
    message = hint.get()
    assert "viz" in message and "pip install" in message, f"unhelpful hint: {message!r}"


def test_failed_layout_leaks_no_output_before_raising(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The layout runs before printing, so a raise leaves no dangling legend."""
    import daedalus.cli.render._topology as topo
    from daedalus.cli.console import out
    from daedalus.cli.render._ascii_dag import GraphLayoutUnavailable

    def _no_layout(*args: object, **kwargs: object) -> None:
        raise GraphLayoutUnavailable("grandalf absent")

    monkeypatch.setattr(topo, "draw_dag", _no_layout)
    payload = _visualize_payload()
    with out.capture() as captured, pytest.raises(GraphLayoutUnavailable):
        topo.lab_visualize_graph(payload, style="full")
    assert captured.get() == "", f"leaked output before the raise:\n{captured.get()!r}"
