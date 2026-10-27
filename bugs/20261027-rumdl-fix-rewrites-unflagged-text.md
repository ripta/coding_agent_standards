# rumdl's fix mode rewrites text that check mode does not flag

**Status:** fixed

**Component:** rumdl 0.1.52, `rumdl check --fix` and `rumdl fmt`. Not this repo's code.

**Reproduces on:** rumdl 0.1.52, with and without this repo's `.rumdl.toml`. Fixed in 0.3.0, checked with the repro
below on 2026-10-27.

## Observed behavior

Fix mode makes two kinds of change that corrupt the file:

1. **Fenced markdown examples.** Inside a ```` ```markdown ```` fence, fix mode adds a blank line after each heading and
   narrows `│  └─` to `│ └─`. `rumdl check` reports nothing for those lines. The fences in this repo are templates
   that show an exact format, such as the ADR template in `claude/project-management/design.md` and the tree in
   `claude/skills/rca/SKILL.md`.
2. **A false MD038 whose fix joins lines.** A bare `$` in prose, followed by code spans that hold `${`, makes rumdl
   report "Spaces inside code span elements" on a line break between two spans. Its fix deletes the line break with no
   space, which leaves "Commits follow`${ROOT}/b.md`". Removing either the `$` or the `{` makes the finding go away,
   which suggests the `$` pairs up as inline math. `claude/commands/guardian.md` has this shape.

`rumdl check --fix` exits 1 while an unfixable finding remains. `rumdl fmt` makes the same rewrites and exits 0.

## First seen

On 2026-10-27, when the format hook ran `make fmt` over this repo. See
`20261027-fmt-hook-formats-wrong-repo.md`. The rewrites were reverted.

## Repro

Run these in an empty directory:

```sh
printf '# T\n\nAct in $ARGUMENTS by following\n`${ROOT}/a.md`. Commits follow\n`${ROOT}/b.md` and\n`${ROOT}/c.md`.\n' > span.md
printf '# T\n\nExample:\n\n```markdown\n## Context\nWhat problem?\n\n- a\n  │  └─ b\n```\n' > fence.md
rumdl check span.md fence.md
rumdl check --fix span.md fence.md
cat span.md fence.md
```

**Still broken:** `check` flags only MD038 at `span.md:4:14`. Afterwards, lines 4 and 5 of `span.md` are joined as
"Commits follow`${ROOT}/b.md` and", and `fence.md` has a blank line after `## Context` and reads `│ └─ b`.

**Fixed:** `check` reports nothing, and `--fix` leaves both files unchanged.

## Fix

rumdl's changelog names three fixes that cover these cases. 0.2.4 gates formatting of markdown code blocks behind an
opt-in. 0.2.53 stops deleting a line when trimming a multi-line code span. 0.2.74 stops reading a math span through a
code span. Only 0.3.0 was run against the repro.

`rumdl/lint-markdown` refuses rumdl older than 0.3.0, and names the upgrade command.
