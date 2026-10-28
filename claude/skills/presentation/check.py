#!/usr/bin/env python3
"""Static checks for a presenterm deck written by the presentation skill.

presenterm cannot render from a non-interactive shell, so this reads the markdown instead. It
reports errors that would break the deck when it loads, and warnings for slides that break the
density limits in style.md.

Usage: check.py <slides.md> [--notes checklist|script] [--terminal NAME]

Exits 1 when there is at least one error, 0 otherwise.
"""

import argparse
import os
import re
import shutil
import sys
from dataclasses import dataclass, field

# Mirrors `presenterm --list-comment-commands` as of 0.16.1, plus the spellings it also accepts.
KNOWN_COMMANDS = {
    "pause",
    "end_slide",
    "new_line",
    "newline",
    "new_lines",
    "newlines",
    "jump_to_middle",
    "column_layout",
    "column",
    "reset_layout",
    "incremental_lists",
    "no_footer",
    "font_size",
    "alignment",
    "skip_slide",
    "list_item_newlines",
    "include",
    "speaker_note",
    "snippet_output",
    "comment",
}

# Mermaid diagram kinds d2 cannot draw. Any other Mermaid kind belongs in d2.
MERMAID_ONLY = {"gantt", "timeline", "sankey", "sankey-beta", "pie", "xychart", "xychart-beta",
                "quadrantchart", "gitgraph"}

MIN_DIAGRAM_NODES = 5

# d2 keywords that can open a line but never name a node.
D2_RESERVED = {"direction", "vars", "classes", "style", "label", "shape", "icon", "near", "width",
               "height", "title", "layers", "scenarios", "steps", "grid-rows", "grid-columns",
               "grid-gap", "tooltip", "link", "constraint", "class"}
D2_EDGE = re.compile(r"\s*(?:<->|->|<-|--)\s*")

MAX_BULLETS = 5
MAX_BULLET_CHARS = 60
MAX_BODY_WORDS = 40
MAX_TABLE_ROWS = 6
MAX_TABLE_COLS = 5
MAX_CODE_LINES = 12
MAX_CHECKLIST_BULLETS = 5
MAX_CHECKLIST_WORDS = 10

FENCE = re.compile(r"^(\s*)(`{3,}|~{3,})(.*)$")
COMMENT = re.compile(r"^\s*<!--\s*(.*?)\s*-->\s*$")
BULLET = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$")
IMAGE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)[^)]*\)")
TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$")
TABLE_SEP = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$")


@dataclass
class Block:
    lang: str
    attrs: str
    start: int
    lines: list = field(default_factory=list)


@dataclass
class Slide:
    number: int
    start: int
    lines: list = field(default_factory=list)  # (line number, text), code and comments removed
    blocks: list = field(default_factory=list)
    commands: list = field(default_factory=list)  # (line number, name, argument)
    notes: list = field(default_factory=list)  # (line number, note text)
    title: str = ""


class Report:
    def __init__(self):
        self.errors = 0
        self.warnings = 0

    def error(self, line, msg):
        self.errors += 1
        print(f"ERROR line {line}: {msg}")

    def warn(self, line, msg):
        self.warnings += 1
        print(f"WARN  line {line}: {msg}")


def strip_front_matter(lines):
    if not lines or lines[0].strip() != "---":
        return {}, 0

    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return {"text": "\n".join(lines[1:i])}, i + 1

    return {}, 0


def parse(lines, offset, report):
    slides = [Slide(number=1, start=offset + 1)]
    block = None
    comment = None

    for i in range(offset, len(lines)):
        lineno = i + 1
        text = lines[i]
        slide = slides[-1]

        if block is not None:
            m = FENCE.match(text)
            if m and m.group(2)[0] == block.fence[0] and len(m.group(2)) >= len(block.fence) \
                    and not m.group(3).strip():
                slide.blocks.append(block)
                block = None
            else:
                block.lines.append(text)
            continue

        if comment is not None:
            if "-->" in text:
                comment.append(text.split("-->", 1)[0])
                handle_multiline_comment(slide, comment, report)
                comment = None
            else:
                comment.append(text)
            continue

        m = FENCE.match(text)
        if m:
            info = m.group(3).strip()
            lang, _, attrs = info.partition(" ")
            block = Block(lang=lang.lower(), attrs=attrs, start=lineno)
            block.fence = m.group(2)
            continue

        m = COMMENT.match(text)
        if m:
            body = m.group(1)
            if body.startswith("//"):
                continue

            name, _, arg = body.partition(":")
            name = name.strip()
            arg = arg.strip()
            if name == "end_slide":
                slides.append(Slide(number=len(slides) + 1, start=lineno + 1))
                continue

            if name == "speaker_note":
                slide.notes.append((lineno, arg))
            slide.commands.append((lineno, name, arg))
            continue

        if text.lstrip().startswith("<!--") and "-->" not in text:
            comment = [(lineno, text.lstrip()[4:])]
            continue

        slide.lines.append((lineno, text))

    if block is not None:
        report.error(block.start, "code fence is never closed")
    if comment is not None:
        report.error(comment[0][0], "HTML comment is never closed")

    return slides


def handle_multiline_comment(slide, comment, report):
    lineno = comment[0][0]
    rest = [c if isinstance(c, str) else c[1] for c in comment[1:]]
    first = comment[0][1].strip()
    body = [first] + rest if first else rest
    body = [b for b in body if b.strip()]
    if not body:
        return

    head = body[0].strip()
    if not head.startswith("speaker_note:"):
        return

    inline = head[len("speaker_note:"):].strip()
    if inline and inline != "|":
        slide.notes.append((lineno, inline))
        return

    slide.notes.append((lineno, "\n".join(b.strip() for b in body[1:])))


def find_title(slide):
    content = [(n, t) for n, t in slide.lines if t.strip()]
    for idx, (n, t) in enumerate(content[:-1]):
        nxt = content[idx + 1][1].strip()
        if re.fullmatch(r"=+|-+", nxt):
            return t.strip()
        break

    return ""


def check_slide(slide, args, deck_dir, report, is_appendix):
    label = f"slide {slide.number}"
    slide.title = find_title(slide)
    is_divider = any(name == "jump_to_middle" for _, name, _ in slide.commands)

    if not slide.title and not is_divider and slide.lines and any(t.strip() for _, t in slide.lines):
        report.warn(slide.start, f"{label} has no setext title (a line of === or --- under the title)")

    layout_cols = None
    for lineno, name, arg in slide.commands:
        if name not in KNOWN_COMMANDS:
            report.error(lineno, f"{label}: unknown comment command '{name}'")
            continue

        if name == "font_size" and args.terminal != "kitty":
            report.warn(lineno, f"{label}: font_size only works in kitty; this deck targets "
                                f"{args.terminal or 'an unknown terminal'}")

        if name == "column_layout":
            nums = re.findall(r"\d+", arg)
            layout_cols = len(nums)
            if not nums:
                report.error(lineno, f"{label}: column_layout needs a list such as [3, 2]")

        if name == "column":
            if layout_cols is None:
                report.error(lineno, f"{label}: column used before any column_layout")
            elif not arg.isdigit() or int(arg) >= layout_cols:
                report.error(lineno, f"{label}: column {arg} is outside a {layout_cols}-column layout")

        if name == "reset_layout":
            layout_cols = None

        if name == "include":
            path = os.path.join(deck_dir, arg)
            if not os.path.exists(path):
                report.error(lineno, f"{label}: included file {arg} does not exist")

    for lineno, text in slide.lines:
        for target in IMAGE.findall(text):
            if re.match(r"^[a-z]+://", target):
                report.error(lineno, f"{label}: remote image {target} is not supported; copy it beside the deck")
            elif not os.path.exists(os.path.join(deck_dir, target)):
                report.error(lineno, f"{label}: image {target} does not exist")

    for block in slide.blocks:
        check_block(block, label, report, is_appendix)

    if is_appendix:
        return

    check_density(slide, label, report)


def check_block(block, label, report, is_appendix):
    if block.lang == "d2":
        if "+render" not in block.attrs:
            report.error(block.start, f"{label}: d2 block without +render shows as source code")
        if shutil.which("d2") is None:
            report.error(block.start, f"{label}: d2 is not installed; run: brew install d2")
        check_thin_diagram(block, label, report)
        return

    if block.lang == "mermaid":
        kind = next((ln.strip().split()[0].lower() for ln in block.lines if ln.strip()
                     and not ln.strip().startswith("%%") and not ln.strip().startswith("---")), "")
        if kind not in MERMAID_ONLY:
            report.warn(block.start, f"{label}: mermaid '{kind}' is drawable in d2; rewrite it in d2")
        if "+render" not in block.attrs:
            report.error(block.start, f"{label}: mermaid block without +render shows as source code")
        if shutil.which("mmdc") is None:
            report.error(block.start, f"{label}: mmdc is not installed; use a table instead, or "
                                      "run: npm install -g @mermaid-js/mermaid-cli")
        return

    if block.lang == "file":
        return

    visible = [ln for ln in block.lines if not ln.lstrip().startswith("/// ")]
    if not is_appendix and len(visible) > MAX_CODE_LINES:
        report.warn(block.start, f"{label}: code block has {len(visible)} lines (limit "
                                 f"{MAX_CODE_LINES}); use highlight frames or move it to the appendix")


def d2_graph(lines):
    """Return the node ids and undirected edges of a flat d2 diagram, or None when it is not flat.

    This is a heuristic, not a d2 parser. A diagram with containers, style maps, or a sequence
    diagram shape returns None, since its shape can carry a claim that node counts do not see.
    """
    nodes = set()
    edges = set()

    for raw in lines:
        text = raw.split("#", 1)[0].strip()
        if not text:
            continue

        if "{" in text or "sequence_diagram" in text:
            return None

        if D2_EDGE.search(text):
            chain = text.rsplit(":", 1)[0] if ":" in D2_EDGE.split(text)[-1] else text
            parts = [p.strip().strip("\"'") for p in D2_EDGE.split(chain) if p.strip()]
            nodes.update(parts)
            edges.update(frozenset(pair) for pair in zip(parts, parts[1:]) if pair[0] != pair[1])
            continue

        key = text.split(":", 1)[0].strip().strip("\"'").split(".", 1)[0]
        if key and key not in D2_RESERVED:
            nodes.add(key)

    return nodes, edges


def check_thin_diagram(block, label, report):
    graph = d2_graph(block.lines)
    if graph is None:
        return

    nodes, edges = graph
    if len(nodes) < MIN_DIAGRAM_NODES:
        report.warn(block.start, f"{label}: d2 diagram has {len(nodes)} nodes (floor "
                                 f"{MIN_DIAGRAM_NODES}); write the sentence it says instead")
        return

    degree = {n: 0 for n in nodes}
    for edge in edges:
        for n in edge:
            degree[n] += 1

    if len(edges) == len(nodes) - 1 and max(degree.values()) <= 2:
        report.warn(block.start, f"{label}: d2 diagram is a straight chain; write the sentence "
                                 "it says instead")


def check_density(slide, label, report):
    bullets = []
    table_rows = 0
    table_cols = 0
    words = 0
    prose_run = 0
    title_seen = False

    for lineno, text in slide.lines:
        stripped = text.strip()
        if not stripped or re.fullmatch(r"=+|-{3,}", stripped):
            prose_run = 0
            continue

        if not title_seen and stripped == slide.title:
            title_seen = True
            continue

        if TABLE_ROW.match(text):
            if not TABLE_SEP.match(text):
                table_rows += 1
                table_cols = max(table_cols, stripped.strip("|").count("|") + 1)
            continue

        if stripped.startswith("#") or stripped.startswith(">"):
            words += len(stripped.lstrip("#> ").split())
            continue

        m = BULLET.match(text)
        if m:
            prose_run = 0
            if not m.group(1):
                bullets.append((lineno, m.group(3)))
            words += len(m.group(3).split())
            continue

        words += len(stripped.split())
        prose_run += len(re.findall(r"[.!?](\s|$)", stripped))
        if prose_run >= 2:
            report.warn(lineno, f"{label}: running prose; a slide carries no paragraphs")
            prose_run = -100

    if len(bullets) > MAX_BULLETS:
        report.warn(bullets[0][0], f"{label}: {len(bullets)} bullets (limit {MAX_BULLETS})")

    for lineno, text in bullets:
        if len(text) > MAX_BULLET_CHARS:
            report.warn(lineno, f"{label}: bullet is {len(text)} characters (limit {MAX_BULLET_CHARS})")

    if table_rows - 1 > MAX_TABLE_ROWS:
        report.warn(slide.start, f"{label}: table has {table_rows - 1} rows (limit {MAX_TABLE_ROWS})")
    if table_cols > MAX_TABLE_COLS:
        report.warn(slide.start, f"{label}: table has {table_cols} columns (limit {MAX_TABLE_COLS})")

    if words > MAX_BODY_WORDS:
        report.warn(slide.start, f"{label}: {words} words of body text (limit {MAX_BODY_WORDS})")


def check_notes(slides, args, report, appendix_start):
    for slide in slides:
        if appendix_start is not None and slide.number >= appendix_start:
            continue

        is_divider = any(name == "jump_to_middle" for _, name, _ in slide.commands)
        if not slide.notes and not is_divider and slide.title:
            report.warn(slide.start, f"slide {slide.number} has no speaker note")

        if args.notes != "checklist":
            continue

        for lineno, note in slide.notes:
            items = [ln.strip() for ln in note.splitlines() if ln.strip()]
            if len(items) > MAX_CHECKLIST_BULLETS:
                report.warn(lineno, f"slide {slide.number}: checklist note has {len(items)} items "
                                    f"(limit {MAX_CHECKLIST_BULLETS})")
            for item in items:
                n = len(item.lstrip("-* ").split())
                if n > MAX_CHECKLIST_WORDS:
                    report.warn(lineno, f"slide {slide.number}: checklist item has {n} words "
                                        f"(limit {MAX_CHECKLIST_WORDS}): {item[:40]}")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("deck")
    parser.add_argument("--notes", choices=["checklist", "script"], default=None)
    parser.add_argument("--terminal", default=os.environ.get("TERM_PROGRAM", "").lower() or None,
                        help="terminal the deck targets; defaults to $TERM_PROGRAM")
    args = parser.parse_args()

    if args.terminal and "kitty" in args.terminal:
        args.terminal = "kitty"
    if os.environ.get("TERM", "") == "xterm-kitty":
        args.terminal = "kitty"

    with open(args.deck, encoding="utf-8") as f:
        lines = f.read().splitlines()

    report = Report()
    front, offset = strip_front_matter(lines)
    if not front:
        report.error(1, "no front matter; the deck needs at least a title and a theme")
    elif "theme:" not in front["text"]:
        report.warn(1, "front matter sets no theme")

    slides = parse(lines, offset, report)
    slides = [s for s in slides if s.lines or s.blocks or s.commands or s.notes]
    for i, slide in enumerate(slides, start=1):
        slide.number = i

    appendix_start = None
    deck_dir = os.path.dirname(os.path.abspath(args.deck))
    for slide in slides:
        slide.title = find_title(slide)
        if appendix_start is None and slide.title.lower().startswith("appendix"):
            appendix_start = slide.number

        is_appendix = appendix_start is not None and slide.number >= appendix_start
        check_slide(slide, args, deck_dir, report, is_appendix)

    check_notes(slides, args, report, appendix_start)

    main_count = (appendix_start - 1) if appendix_start else len(slides)
    print(f"{len(slides)} slides ({main_count} main, {len(slides) - main_count} appendix): "
          f"{report.errors} errors, {report.warnings} warnings")
    sys.exit(1 if report.errors else 0)


if __name__ == "__main__":
    main()
