#!/usr/bin/env python3
"""Validate a directory of cross-linked Markdown lore pages."""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import unquote, urlsplit


MARKDOWN_LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")
MARKDOWN_IMAGE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
H1 = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".avif"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="Directory containing lore Markdown")
    parser.add_argument(
        "--max-new-images",
        type=int,
        help="Hard maximum number of newly generated images",
    )
    parser.add_argument(
        "--new-image",
        action="append",
        default=[],
        metavar="PATH",
        help="New image path relative to ROOT; repeat for each generated asset",
    )
    return parser.parse_args()


def clean_target(raw: str) -> str | None:
    target = raw.strip()
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1]
    parts = urlsplit(target)
    if parts.scheme or parts.netloc or target.startswith("#"):
        return None
    return unquote(parts.path)


def resolve_local(source: Path, target: str, root: Path) -> Path:
    candidate = (source.parent / target).resolve()
    if candidate.is_dir():
        candidate = candidate / "index.md"
    return candidate


def relative_label(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    errors: list[str] = []
    warnings: list[str] = []

    if not root.is_dir():
        print(f"ERROR: lore directory does not exist: {root}", file=sys.stderr)
        return 2
    if args.max_new_images is not None and args.max_new_images < 0:
        print("ERROR: --max-new-images must be nonnegative", file=sys.stderr)
        return 2
    if args.new_image and args.max_new_images is None:
        print("ERROR: --new-image requires --max-new-images", file=sys.stderr)
        return 2

    markdown_files = sorted(root.rglob("*.md"))
    if not markdown_files:
        errors.append("no Markdown files found")

    titles: defaultdict[str, list[Path]] = defaultdict(list)
    inbound: Counter[Path] = Counter()
    outbound: Counter[Path] = Counter()
    referenced_assets: Counter[Path] = Counter()

    for source in markdown_files:
        text = source.read_text(encoding="utf-8")
        headings = H1.findall(text)
        label = relative_label(source, root)
        if len(headings) != 1:
            errors.append(f"{label}: expected exactly one H1, found {len(headings)}")
        else:
            titles[headings[0].strip()].append(source)

        for raw in MARKDOWN_LINK.findall(text):
            target = clean_target(raw)
            if target is None:
                continue
            resolved = resolve_local(source, target, root)
            if not resolved.exists():
                errors.append(f"{label}: broken link: {raw}")
                continue
            if resolved.suffix.lower() == ".md":
                outbound[source] += 1
                inbound[resolved] += 1

        for raw in MARKDOWN_IMAGE.findall(text):
            target = clean_target(raw)
            if target is None:
                continue
            resolved = resolve_local(source, target, root)
            if not resolved.is_file():
                errors.append(f"{label}: missing image: {raw}")
            else:
                referenced_assets[resolved] += 1

    for title, paths in sorted(titles.items()):
        if len(paths) > 1:
            joined = ", ".join(relative_label(path, root) for path in paths)
            errors.append(f"duplicate H1 {title!r}: {joined}")

    if len(markdown_files) > 1:
        for path in markdown_files:
            label = relative_label(path, root)
            if inbound[path] == 0:
                warnings.append(f"{label}: no inbound Markdown links")
            if outbound[path] == 0:
                warnings.append(f"{label}: no outbound Markdown links")

    new_images: list[Path] = []
    for raw in args.new_image:
        image = (root / raw).resolve()
        new_images.append(image)
        if image.suffix.lower() not in IMAGE_SUFFIXES:
            errors.append(f"new image has unsupported suffix: {raw}")
        if not image.is_file():
            errors.append(f"new image does not exist: {raw}")
        elif referenced_assets[image] == 0:
            warnings.append(f"new image is not referenced by Markdown: {raw}")

    if len(set(new_images)) != len(new_images):
        errors.append("the --new-image list contains duplicate paths")
    if args.max_new_images is not None and len(new_images) > args.max_new_images:
        errors.append(
            f"new-image budget exceeded: {len(new_images)} > {args.max_new_images}"
        )

    for warning in warnings:
        print(f"WARNING: {warning}")
    for error in errors:
        print(f"ERROR: {error}")

    budget = "not supplied"
    if args.max_new_images is not None:
        budget = f"{len(new_images)}/{args.max_new_images}"
    print(
        "SUMMARY: "
        f"markdown={len(markdown_files)} "
        f"local_images={len(referenced_assets)} "
        f"new_image_budget={budget} "
        f"warnings={len(warnings)} errors={len(errors)}"
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
