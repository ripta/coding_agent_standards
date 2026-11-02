"""Tests for check.py's diagram-style rules. Run: uv run --with pytest pytest claude/skills/walkthrough"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

# Both skills ship a check.py, so each test loads its own under a distinct module name.
_spec = importlib.util.spec_from_file_location("walkthrough_check", Path(__file__).parent / "check.py")
check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check)

TEMPLATE = Path(__file__).parent / "template.html"


def _page(tmp_path: Path, diagram: str, script: str = "") -> Path:
    # The shipped template with one extra diagram, so every other rule stays satisfied.
    src = TEMPLATE.read_text()
    figure = f'<figure><div class="mermaid">\n{diagram}\n</div><figcaption>x</figcaption></figure>'
    src = src.replace('<details class="callout definition">', figure + '\n<details class="callout definition">', 1)
    if script:
        src = src.replace("</body>", f"<script>{script}</script>\n</body>", 1)
    page = tmp_path / "page.html"
    page.write_text(src)
    return page


def _report(capsys) -> str:
    return capsys.readouterr().out


def test_the_template_passes_the_diagram_rules(tmp_path: Path, capsys) -> None:
    page = tmp_path / "page.html"
    page.write_text(TEMPLATE.read_text())

    check.check(str(page))

    out = _report(capsys)
    assert "built-in theme" not in out
    assert "handDrawn" not in out
    assert "hex color" not in out


@pytest.mark.parametrize("init", [
    "%%{init: {'theme': 'dark'}}%%",
    '%%{init: {"theme": "forest"}}%%',
    "---\nconfig:\n  theme: neutral\n---",
])
def test_a_built_in_theme_in_diagram_source_is_an_error(tmp_path: Path, capsys, init: str) -> None:
    # Built-in themes put edge labels on fixed greys that fail contrast; the page tokens must win.
    status = check.check(str(_page(tmp_path, init + "\nflowchart LR\n  A --> B")))

    assert status == 1
    assert "built-in theme" in _report(capsys)


def test_a_built_in_theme_in_mermaid_initialize_is_an_error(tmp_path: Path, capsys) -> None:
    status = check.check(str(_page(tmp_path, "flowchart LR\n  A --> B", "mermaid.initialize({theme: 'default'});")))

    assert status == 1
    assert "built-in theme" in _report(capsys)


def test_the_hand_drawn_look_is_an_error(tmp_path: Path, capsys) -> None:
    status = check.check(str(_page(tmp_path, "---\nconfig:\n  look: handDrawn\n---\nflowchart LR\n  A --> B")))

    assert status == 1
    assert "handDrawn" in _report(capsys)


def test_a_hex_color_in_diagram_source_warns(tmp_path: Path, capsys) -> None:
    check.check(str(_page(tmp_path, "flowchart LR\n  A --> B\n  classDef hot fill:#ff0000\n  class A hot")))

    assert "hex color" in _report(capsys)
