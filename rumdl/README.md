# Markdown Linting

Structural checks on markdown, using [rumdl](https://rumdl.dev).

Heading style, list markers, code-fence hygiene, and line length. The line
length is the part worth configuring deliberately. Everything else is close
enough to the defaults to leave alone.

## Two widths, two domains

Markdown prose wraps at **120**. Code and code comments wrap at **100**.

These are different numbers for different things, and they should not be
reconciled. 120 comes from the Markdown Quality section of
`claude/project-management/tracking.md`. 100 comes from
`claude/rules/work-discipline.md` and is enforced by each language's own
formatter: `max_width` in rustfmt, `lineWidth` in Biome, and so on. rumdl never
sees code, so it never has an opinion about the second number.

Code blocks inside markdown are exempt from MD013 for the same reason. A Go
snippet in a fenced block carries Go's width. Holding it to a markdown limit
would fight gofmt.

## Setup

rumdl is a single static binary with no runtime.

```sh
brew install rumdl
```

In the consuming project:

```sh
cp ~/projects/coding_agent_standards/rumdl/rumdl.toml.template .rumdl.toml
```

Trim the `per-file-ignores` entries to the paths the project actually has. Then:

```sh
~/projects/coding_agent_standards/rumdl/lint-markdown
```

Add a `make lint-markdown` target that calls it. The `lint-runner` skill picks
up Makefile targets without further wiring.

## Copy the template, do not symlink it

rumdl has no config inheritance. There is no `extend` key, and `--config <path>`
**replaces** the discovered `.rumdl.toml` rather than merging with it.

This was verified, not assumed. Running `rumdl check --config <shared>` against
this repo dropped its own `per-file-ignores` and started reporting MD041 on
every `SKILL.md`.

So each project keeps a real copy and re-syncs by hand when the template
changes. This repo's own `.rumdl.toml` is one such copy. Change it and the
template together.

## A missing config looks like a clean repo

Without a `.rumdl.toml`, rumdl falls back to built-in defaults, where MD013 is
**80**. The run still succeeds. It just enforces a width nobody agreed to.

That is exactly what happened here before this directory existed. `.rumdl.toml`
set `per-file-ignores` and nothing else, so the documented standard was 120 and
the enforced one was 80. The gap went unnoticed because both numbers produce a
plausible-looking run.

`lint-markdown` refuses to run without a `.rumdl.toml` for this reason.

## Lint the diff, not the tree

`lint-markdown` defaults to files changed against the base ref, matching
`vale/lint-prose`. Use `--all` for a report. Never gate CI on `--all`.

The backlog argument is weaker here than it is for Vale, because MD013 carries a
fix. `lint-markdown --all --fix` clears the whole line-length backlog in one
pass. Run it once at adoption, then leave the default scoping in place for
everything that has no autofix.

## Reflow only touches what is broken

`reflow = true` is what makes `--fix` able to rewrap prose. It is safe to enable
on a repo with hand-wrapped markdown.

Reflow rewraps only paragraphs that contain a violation. A paragraph already
under the limit is left byte-for-byte alone. `claude/skills/cloudbuild/SKILL.md`
is hand-wrapped at about 78 columns and reports zero findings, unchanged.

Turn it off in a project that uses semantic line breaks, where one sentence per
line is deliberate. Reflow would join those up to 120 and destroy the intent.

## Relationship to the other tools

`vale/` checks prose shape in markdown and in code comments: sentence length and
paragraph length. rumdl checks markdown structure. They do not overlap. Run
both.

`claude/agents/reviewer.md` keeps the comment checks that need judgment, and the
100-column comment width lives there rather than here.

## Known backlog in this repo

MD013 is clean across all 92 files. 64 findings remain in other rules, almost
all of them pre-existing:

| rule | count | what it is |
|---|---|---|
| MD040 | 28 | fenced code block with no language tag |
| MD032 | 16 | list not preceded by a blank line |
| MD022 | 8 | heading missing a blank line above or below |
| MD031 | 7 | fenced block missing a surrounding blank line |
| MD057 | 3 | relative link to a file that does not exist |
| MD049 | 1 | inconsistent emphasis style |
| MD038 | 1 | spaces inside a code span |

61 of the 64 are autofixable. MD040 is worth doing by hand. rumdl guesses the
language tag, and a wrong tag is worse than a missing one.
