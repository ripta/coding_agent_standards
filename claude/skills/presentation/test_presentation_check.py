"""Tests for check.py's d2 diagram checks. Run: uv run --with pytest pytest claude/skills/presentation"""

from __future__ import annotations

import importlib.util
from pathlib import Path

# Both skills ship a check.py, so each test loads its own under a distinct module name.
_spec = importlib.util.spec_from_file_location("presentation_check", Path(__file__).parent / "check.py")
check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check)

STYLE = """vars: {
  d2-config: {
    layout-engine: elk
    theme-overrides: {
      N1: "#1b2230"
      B6: "#eef1f6"
    }
  }
}
"""


def _graph(body: str):
    return check.d2_graph(body.splitlines())


def test_a_style_block_does_not_hide_a_thin_chain() -> None:
    # Every deck diagram carries a vars block for its palette and layout. The thin-diagram
    # heuristic must still see the chain under it, or the warning silently stops firing.
    graph = _graph(STYLE + "a -> b -> c\n")

    assert graph is not None
    nodes, edges = graph
    assert nodes == {"a", "b", "c"}
    assert len(edges) == 2


def test_a_container_still_opts_out() -> None:
    assert _graph(STYLE + "prod: Production {\n  ec2: EC2\n}\npayer -> prod\n") is None


def test_style_warnings_name_what_is_missing(capsys) -> None:
    # A block without overrides shows presenterm's built-in d2 palette, which the standard rules out.
    report = check.Report()
    block = check.Block(lang="d2", attrs="+render", start=1, lines=["a -> b"])

    check.check_d2_style(block, "slide 1", report)

    out = capsys.readouterr().out
    assert report.warnings == 2
    assert "theme-overrides" in out
    assert "layout-engine: elk" in out


def test_a_styled_block_passes() -> None:
    report = check.Report()
    block = check.Block(lang="d2", attrs="+render", start=1, lines=(STYLE + "a -> b").splitlines())

    check.check_d2_style(block, "slide 1", report)

    assert report.warnings == 0
