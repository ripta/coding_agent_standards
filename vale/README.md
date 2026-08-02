# Prose Linting

Deterministic checks on prose and code comments, using [Vale](https://vale.sh).

Two rules only. Sentences stay under 30 words. Paragraphs stay under 6
sentences. Both numbers were calibrated against real repos, not copied from a
style guide.

These rules cover the countable part of `claude/rules/sentence-structure.md`.
They do not replace it. Everything that needs judgment stays with the reviewer
agent.

## What this does not do

There is no approved-word list, no banned-word list, and no register control.
Vocabulary and punctuation stay as `claude/rules/writing-voice.md` describes
them. Vale never sees them.

## Setup

Vale is a single static binary with no runtime.

```sh
brew install vale
```

In the consuming project:

```sh
mkdir -p .vale
ln -s ~/projects/coding_agent_standards/vale/styles .vale/styles
cp ~/projects/coding_agent_standards/vale/vale.ini.template .vale.ini
```

Trim the globs in `.vale.ini` to the languages the project has. Then:

```sh
~/projects/coding_agent_standards/vale/lint-prose
```

Add a `make lint-prose` target that calls it. The `lint-runner` skill picks up
Makefile targets without further wiring.

## Lint the diff, not the tree

`lint-prose` defaults to files changed against the base ref. That is
deliberate.

Every repo carries a backlog. Across eight projects the full-tree run produces
2,796 findings. Nobody burns that down, so it gets suppressed and the rule dies.
Diff scoping puts the same threshold on new work only, where it yields a handful
per change.

Use `--all` for a report. Never gate CI on `--all`.

## Language coverage

Covered: C, C++, C#, Go, Java, JavaScript, Lua, PHP, protobuf, Python, Ruby,
Rust, Scala, Swift, TypeScript.

Not covered: **Zig**, **Svelte**, **1z**. Vale has no lexer for them. Comments
in those languages stay reviewer-enforced. Markdown in those projects is still
linted normally.

Do not try to add an unsupported language through `[formats]`. It does not add
support. Vale treats the file as plain markdown and lints the source code itself
as prose. A Zig file with no comments at all reported two warnings on live code
lines during testing.

## Two traps, both verified

**The `[formats]` block is required.** Without it, `scope: sentence` and
`scope: paragraph` match nothing inside code comments. Vale still extracts the
comments. The scopes just never resolve. The run reports zero findings and looks
like a clean repo. Mapping an extension to `md` makes Vale parse each comment
body as markdown, which is what makes the scopes work.

Verify the config against a file you know should trip. A clean run proves
nothing.

**Emoji pseudo-lists read as one enormous sentence.** Lines like
`✅ **Fast**: does the thing`, separated by trailing-double-space hard breaks
rather than list markers, parse as a single paragraph with no sentence-ending
punctuation. One repo reported a 72-word sentence that was really seven short
bullets. `BlockIgnores` in the template handles it. The durable fix is to write
them as real list items.

## Known gaps

- Indented bullets inside a comment are skipped entirely. After `//` stripping
  the indent reads as a code block. This under-reports rather than
  false-positives, but list-form doc comments get less coverage than the
  numbers suggest.
- `ParagraphLength` is off for code comments in the template. It was calibrated
  on markdown only. Turn it on per project once you have seen what it reports.

## Relationship to the other tools

`rumdl` checks markdown structure: heading style, list markers, line length,
proper-noun casing. Vale checks prose shape in markdown and in code comments.
They do not overlap. Run both.

`claude/agents/reviewer.md` keeps the comment checks that need judgment. Whether
a comment restates the code. Whether it sits on the right function. Whether the
"why" is already documented somewhere canonical. Vale takes the counting so the
reviewer does not spend attention on it.

## Rollout order

Measured findings per repo, full tree, with this exact config:

| tier | repo | findings | note |
|---|---|---|---|
| 1 | hotpod | 5 | Go only, smoke test |
| 1 | electron_microscope | 32 | Go + TS + protobuf, real validation |
| 2 | sprout-n-shelve | 48 | TypeScript |
| 2 | zaz | 107 | Rust, heavily commented |
| 3 | rt | 198 | |
| 3 | mochi | 273 | |
| 3 | worldwiki-au | 898 | worst comment divergence in the set |
| 3 | elastane | 1,235 | largest backlog |
| 4 | 1z | markdown only | Zig comments not lintable |

Tier 1 is small enough to fix tree-wide in an afternoon. Tiers 2 and 3 are
diff-scoped. By the end of tier 2 the config has been proven against Go,
TypeScript, and Rust, which is all the coverage that matters here.
