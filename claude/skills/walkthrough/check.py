#!/usr/bin/env python3
"""Mechanical checks for a walkthrough page.

Checks the things a reader cannot: that the file is genuinely self-contained, that
its internal links resolve, that the theme machinery is wired, and that every
library it uses is actually loaded at a pinned version.

    python3 check.py page.html

Exit status is 1 when there is at least one ERROR. Warnings never fail the run;
judge them and fix the ones that matter.
"""

from __future__ import annotations

import re
import sys
from html.parser import HTMLParser

VOID = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
}
# Elements whose end tag HTML lets you omit. Never reported as unclosed.
OPTIONAL_END = {
    "p", "li", "dt", "dd", "td", "th", "tr", "thead", "tbody", "tfoot",
    "option", "colgroup", "rt", "rp", "head", "body", "html",
}
SELF_CLOSING_SIBLING = {"li", "td", "th", "tr", "option", "dt", "dd", "p"}

# Schemes that survive being uploaded to a static file server.
REMOTE = ("https://", "mailto:", "data:", "//")

ASCII_ART = set(" +-|/\\<>v^_=*.:")


class Page(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.errors: list[tuple[int, str]] = []
        self.warns: list[tuple[int, str]] = []
        self.stack: list[tuple[str, int]] = []
        self.ids: dict[str, int] = {}
        self.refs: list[tuple[str, int, str]] = []   # (target, line, kind)
        self.scripts: list[tuple[str, int]] = []     # (src, line)
        self.classes: set[str] = set()
        self.markers: set[str] = set()
        self.notes: set[str] = set()
        self.title = ""
        self._in: str | None = None
        self._buf: list[str] = []
        self._pres: list[tuple[str, int]] = []
        self._pre_line = 0

    # -- reporting ------------------------------------------------------
    def err(self, msg: str, line: int | None = None) -> None:
        self.errors.append((line if line is not None else self.getpos()[0], msg))

    def warn(self, msg: str, line: int | None = None) -> None:
        self.warns.append((line if line is not None else self.getpos()[0], msg))

    # -- parsing --------------------------------------------------------
    def handle_starttag(self, tag, attrs):
        line = self.getpos()[0]
        a = {k: (v or "") for k, v in attrs}

        if "id" in a:
            if a["id"] in self.ids:
                self.err(f"duplicate id {a['id']!r} (first at line {self.ids[a['id']]})", line)
            else:
                self.ids[a["id"]] = line
        for cls in a.get("class", "").split():
            self.classes.add(cls)
        if "data-mk" in a:
            self.markers.add(a["data-mk"])
        if "data-mk-note" in a:
            self.notes.add(a["data-mk-note"])
        if "aria-controls" in a:
            self.refs.append((a["aria-controls"], line, "aria-controls"))

        if tag == "script" and "src" in a:
            self.scripts.append((a["src"], line))
            self._check_remote("script src", a["src"], line)
        if tag in ("link", "img", "iframe", "source", "video", "audio", "embed"):
            for key in ("href", "src"):
                if key in a:
                    self._check_remote(f"<{tag} {key}>", a[key], line)
        if tag == "a" and "href" in a:
            self._check_link(a, line)

        if tag == "pre":
            self._pre_line = line
        if tag in ("script", "style", "pre", "title"):
            self._in, self._buf = tag, []
        if tag in VOID:
            return
        if self.stack and tag in SELF_CLOSING_SIBLING and self.stack[-1][0] == tag:
            self.stack.pop()
        self.stack.append((tag, line))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID and self.stack and self.stack[-1][0] == tag:
            self.stack.pop()

    def handle_endtag(self, tag):
        if self._in == tag:
            text = "".join(self._buf)
            if tag == "title":
                self.title = text.strip()
            elif tag == "pre":
                self._pres.append((text, self._pre_line))
            self._in, self._buf = None, []
        if tag in VOID:
            return
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                for name, line in self.stack[i + 1:]:
                    if name not in OPTIONAL_END:
                        self.err(f"<{name}> opened here is never closed", line)
                del self.stack[i:]
                return
        self.err(f"stray closing </{tag}> with no matching open tag")

    def handle_data(self, data):
        if self._in:
            self._buf.append(data)

    # -- link rules -----------------------------------------------------
    def _check_remote(self, what: str, url: str, line: int) -> None:
        if url.startswith("#") or url.startswith(REMOTE):
            return
        if url.startswith("http://"):
            self.err(f"{what} uses plain http: {url}", line)
        elif url.startswith("file://"):
            self.err(f"{what} points at the local filesystem: {url}", line)
        else:
            self.err(f"{what} is a local path, so the page is not self-contained: {url}", line)

    def _check_link(self, a: dict, line: int) -> None:
        href = a["href"]
        if href == "#":
            self.warn("placeholder link href=\"#\"", line)
        elif href.startswith("#"):
            self.refs.append((href[1:], line, "anchor"))
        elif href.startswith(REMOTE) or href.startswith("http://"):
            if a.get("target") == "_blank" and "noopener" not in a.get("rel", ""):
                self.warn("external link with target=_blank is missing rel=\"noopener noreferrer\"", line)
        elif href.startswith("file://"):
            self.err(f"link points at the local filesystem: {href}", line)
        else:
            self.err(f"link to a relative path will 404 when served standalone: {href}", line)


def check(path: str) -> int:
    with open(path, encoding="utf-8") as fh:
        src = fh.read()

    p = Page()
    p.feed(src)
    p.close()

    for name, line in p.stack:
        if name not in OPTIONAL_END:
            p.err(f"<{name}> opened here is never closed", line)

    if not re.match(r"\s*<!DOCTYPE html>", src, re.IGNORECASE):
        p.err("missing <!DOCTYPE html>", 1)
    if not p.title or "REPLACE" in p.title:
        p.err("the <title> is missing or still a placeholder", 1)

    for target, line, kind in p.refs:
        if target not in p.ids:
            p.err(f"{kind} points at #{target}, which no element defines", line)

    # Template placeholders must not ship.
    holes = [src.count("\n", 0, m.start()) + 1 for m in re.finditer(r"REPLACE", src)]
    if holes:
        tail = f" (and {len(holes) - 1} more)" if len(holes) > 1 else ""
        p.err(f"template placeholder REPLACE is still in the page{tail}", holes[0])

    # Theme machinery.
    for needle, msg in (
        ("data-theme", "no data-theme attribute, so the color tokens never switch"),
        ("prefers-color-scheme", "the page never reads the system color preference"),
        ("localStorage", "the theme choice is not persisted to localStorage"),
    ):
        if needle not in src:
            p.err(msg, 1)
    if not re.search(r"<button[^>]*id=[\"']theme-toggle", src):
        p.warn("no #theme-toggle button found; make sure the toggle is reachable", 1)

    # Libraries: loaded but unused, or used but not loaded.
    loaded = {"mermaid": False, "d3": False, "chart": False}
    for url, line in p.scripts:
        low = url.lower()
        for key in loaded:
            if re.search(rf"/{key}[./@-]", low) or f"/{key}.min.js" in low:
                loaded[key] = True
        if re.search(r"/(latest|next|master|main)/", low) or "@latest" in low or "@next" in low:
            p.err(f"CDN URL is not pinned to an exact version: {url}", line)

    # Scan for usage with the CDN <script src> tags removed: their own URLs
    # contain the library names and would otherwise count as usage.
    body = re.sub(r"<script[^>]*\bsrc=[^>]*>\s*</script>", "", src, flags=re.IGNORECASE)
    used = {
        "mermaid": "mermaid" in p.classes or "mermaid.initialize" in body,
        "d3": bool(re.search(r"\bd3\.\w", body)),
        "chart": bool(re.search(r"new\s+Chart\s*\(", body)),
    }
    names = {"mermaid": "Mermaid", "d3": "D3", "chart": "Chart.js"}
    for key, is_used in used.items():
        if is_used and not loaded[key]:
            p.err(f"{names[key]} is used but never loaded from a CDN", 1)
        if loaded[key] and not is_used:
            p.warn(f"{names[key]} is loaded but never used; drop the <script> tag", 1)

    if used["chart"] and "registerChart" not in src:
        p.warn("charts are created without registerChart(); they will not follow the theme toggle", 1)
    if used["mermaid"] and "themechange" not in src:
        p.warn("no themechange handler; Mermaid diagrams keep their old colors after a toggle", 1)

    # Hardcoded colors defeat the theme toggle.
    for m in re.finditer(r"<svg\b.*?</svg>", src, re.DOTALL | re.IGNORECASE):
        if re.search(r"(fill|stroke)\s*=\s*[\"']#[0-9a-f]{3,8}", m.group(0), re.IGNORECASE):
            p.warn("inline SVG hardcodes a color; use class=\"fill-accent\" and friends instead",
                   src.count("\n", 0, m.start()) + 1)
            break
    if re.search(r"(background|border)Color:\s*[\"']#", src):
        p.warn("Chart.js dataset hardcodes a hex color; read it from a CSS custom property", 1)

    # Code markers must be wired in both directions.
    for mk in sorted(p.markers - p.notes):
        p.warn(f"marker {mk} in the code has no matching [data-mk-note]", 1)
    for note in sorted(p.notes - p.markers):
        p.warn(f"note {note} has no matching marker in any code block", 1)

    # ASCII diagrams are never acceptable.
    for text, line in p._pres:
        art = [ln for ln in text.splitlines()
               if len(ln.strip()) >= 8 and set(ln) <= ASCII_ART and any(c in ln for c in "+|")]
        if len(art) >= 2:
            p.warn("this <pre> looks like an ASCII diagram; use Mermaid or SVG", line)

    size = len(src.encode("utf-8"))
    if size > 600_000:
        p.warn(f"page is {size // 1024} KB; consider trimming pasted code", 1)

    for label, items in (("ERROR", p.errors), ("WARN", p.warns)):
        for line, msg in sorted(items):
            print(f"{label} {path}:{line}: {msg}")

    n_err, n_warn = len(p.errors), len(p.warns)
    print(f"\n{n_err} error(s), {n_warn} warning(s), {size // 1024} KB")
    return 1 if n_err else 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__.strip(), file=sys.stderr)
        sys.exit(2)
    sys.exit(check(sys.argv[1]))
