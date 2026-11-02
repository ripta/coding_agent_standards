# LLM Wiki

A wiki is a git repository of written knowledge that people and agents both read and write. Several agent sessions
often work in one checkout at once. This standard sets its layout, its file formats, and the rules that keep those
sessions from colliding.

Each wiki's own `README.md` holds the rules specific to that repository. This standard covers what every wiki shares.

## Layers

A wiki has three layers:

- **Reports** are dated, immutable evidence. Each one is the write-up of one investigation, review, or session.
- **Topics** are living pages. Each states the current position on a subject and links the reports behind it.
- **References** are external material imported verbatim, such as articles, papers, and vendor documentation.

The organizing rule is that paths encode only what never changes. A report's date never changes, so the date decides
its folder. Topics can be renamed, split, or added, so they live in frontmatter. Re-tagging a report never moves it.

```text
index.md              generated catalog: topics, projects, every report
topics/<slug>.md      living topic pages
reports/YYYY/MM/      dated reports, filed by the date in their name
references/           imported external material, kept verbatim
projects/<name>/      optional project folders
wiki.json             index title and intro line
bin/wiki              the wiki tool
```

A wiki has no `guides/` layer. A how-to that stays true belongs on a topic page. A how-to tied to one investigation is
a report.

## Reports

A report is the durable write-up of one investigation, review, or session. Standalone research is a report too. There
is no separate research folder.

- **Name.** `YYYYMMDD-short-slug.md`. The slug names the subject, not the activity.
- **Location.** `reports/YYYY/MM/`, taken from the name, as in `reports/2026/03/20260312-cache-eviction-study.md`. The
  filename keeps the date prefix, so a bare filename cited elsewhere stays unique and greppable.
- **Multi-file reports.** A report with figures or data is a directory with the same name, such as
  `reports/2026/03/20260312-cache-eviction-study/`. Exactly one top-level `.md` in it carries the frontmatter. Prefer
  `README.md` for that file.
- **HTML renderings.** Every report has a Markdown entry. An HTML version, such as a page with charts, is a second
  rendering of it. Put it in a directory report beside the entry, as in
  `reports/2026/03/20260312-cache-eviction-study/report.html`. The tool reads only the entry. A rendering can fall
  behind its entry, including the generated block described under "Later Reports".

### Frontmatter

Every Markdown report starts with frontmatter:

```yaml
---
topics: [caching, storage-engine]
summary: "One sentence stating the finding, for the index."
---
```

- `topics` lists one or more slugs from `topics/`, most relevant first.
- `summary` is one sentence of at most about 25 words. It states the conclusion.
- `title` is optional. Use it only for a report with no `# H1`. Otherwise the H1 is the title.
- `follows` and `corrects` are optional. See "Later Reports".

The date comes from the filename, so the frontmatter does not repeat it.

Older wikis may hold standalone `.html` reports. The tool still indexes them. They carry their data in
`<meta name="topics" content="caching, storage-engine">` and `<meta name="description" content="...">`, and their
`<title>` is their title. `check` warns about each one. Do not add new ones.

### Later Reports

A report names the earlier reports it builds on or overturns:

```yaml
---
topics: [caching]
summary: "LRU's lead holds, but the hit ratios in the first study were overcounted."
follows: [20260320-eviction-follow-up]
corrects: [20260312-cache-eviction-study]
---
```

- `follows` names reports this one builds on.
- `corrects` names reports this one shows were wrong, in whole or in part.
- Each value is a list of report names. A name is the dated basename without its extension, or the directory name of a
  multi-file report.
- A report never names itself, a report dated after it, or one report in both lists.

The body still links back in prose, as before.

`build` writes the forward links into each earlier report. The block sits under the H1, or right after the
frontmatter when the report has no H1. Corrections come first, so a reader meets them before the stale findings:

```markdown
# Cache eviction study

<!-- BEGIN GENERATED: later-reports (wiki build) -->
Later reports:

- Corrected by **2026-04-01** [Hit-ratio recount](../04/20260401-hit-ratio-recount.md)
- Followed by **2026-03-20** [Eviction follow-up](20260320-eviction-follow-up.md)
<!-- END GENERATED -->
```

A report that no later report names has no block. When the last one goes, `build` removes the block and the report is
byte-identical to what its author committed. A multi-file report takes the block in its entry. A standalone HTML
report gets no block.

The index and the topic report lists flag a corrected report with "(corrected by ...)" after its summary. That holds
for standalone HTML reports too.

### Immutability

A report is immutable once committed. Fixing a typo or a broken link is allowed. A new finding goes in a new report,
and the topic page is updated to match. Never rewrite another session's report. Write a new one and link back to it.

The generated later-reports block is the one other change an earlier report takes. `build` writes it. Never hand-write
a forward link, such as a "Follow-up:" line, into an earlier report. Declare `follows` or `corrects` on the new report
instead.

Committing another session's report is allowed only to carry that regenerated block. Commit it with the new report
that changed it. Change nothing else in it.

## Topics

A topic page answers "what do we currently know about X?" The reader should not have to replay every report to learn
it. Pages sit flat in `topics/` with no nesting. The `area` field groups them in the index.

```markdown
---
area: Infrastructure
summary: "One line for the index."
reviewed: 2026-03-12
---

# Caching

What the topic covers and where its edges are.

## Current position

- A claim that is true as of the latest report ([report](../reports/2026/03/20260312-cache-eviction-study.md)).

## Open questions

## Related

## Reports

<!-- BEGIN GENERATED: reports (wiki build) -->
<!-- END GENERATED -->
```

- `area` names the index group. A page without one lands under "Other".
- `summary` is the page's line in the index.
- `reviewed` is the date someone last brought "Current position" up to date with the reports.

When a report changes the current position, update that topic's "Current position" in the same commit as the report.
Bump `reviewed` to the report's date at the same time. When a report only adds evidence, tagging it is enough.

Create a topic page when the first report needs it. The check fails on a tag with no page, which also catches typos.

### Splitting and Renaming

To split or rename a topic, re-tag the affected reports. That is a frontmatter edit, and no report moves. Leave the old
page as a short stub that points at the new pages.

### Concurrent Edits

Several sessions often write reports at the same time, all in the same checkout. The layout keeps them from colliding:

- Reports are new files, so they never conflict.
- `index.md`, the topic report lists, and the later-reports blocks are generated deterministically from tracked
  files. Any session that regenerates them produces the same output.
- The only hand-edited shared text is a topic's "Current position". It changes only when a finding changes it.

Sessions edit "Current position" directly, so topics do not go stale between review passes. Revisit this design if
edits to one topic page start colliding often. The alternative is for sessions only to tag reports. A periodic review
pass then becomes the single writer of topic text. That removes the conflicts, but topics lag until the next pass.

## References

`references/` holds external writings imported verbatim, such as articles, papers, and blog posts. They are sources,
not the wiki's own analysis. They carry a provenance block instead of report frontmatter, and they are never rewritten.

Convert an import to Markdown text rather than committing the original PDF or HTML. Text diffs, greps, and reads
better. Start each converted file with a provenance block that names the source, the URL, the capture date, and how it
was converted:

```markdown
> Source: Example Systems Journal, "Admission Policies for Small Caches"
> URL: https://example.com/papers/admission-policies
> Captured: 2026-03-12
> Converted: PDF to Markdown with pdftotext, tables fixed by hand
```

A figure that does not survive text extraction, such as a chart or a diagram, may be committed as a small image.
Crop it to the figure alone, never a full-page scan, and reference it from the Markdown.

## Projects

The `projects/` layer is optional. A wiki turns it on by tracking files under `projects/`. Git does not track an empty
directory, so the layer appears once the first project file is added.

Each project is a folder, `projects/<name>/`, with a `README.md` at its root. That README's `# H1` is the project's
entry in the index. The README stays short: one paragraph on what the project is, plus pointers to its spec. Each wiki
defines the layout inside a project folder in its own README.

A topic that grows into a project gets a project folder. Earlier reports stay where they are. The project README links
back to the topic, and the topic's "Related" section links to the project.

## File Naming

- Filenames are lowercase kebab-case, such as `cache-eviction.md`.
- Reports are `YYYYMMDD-short-slug.md` under `reports/YYYY/MM/`.
- `README.md` is the one exception. It keeps the conventional uppercase.

## The Wiki Tool

`bin/wiki` runs the tool:

```text
bin/wiki build    regenerate index.md, the topic report lists, and the later-reports blocks
bin/wiki check    lint; fails on anything invalid or stale
bin/wiki stale    list topics with reports newer than their `reviewed` date
```

`check` verifies these:

- Every report is named `YYYYMMDD-slug` and filed under the month in its name.
- No dated report sits at the repository root.
- Every report has frontmatter with topics and a summary.
- A directory report has exactly one top-level `.md` carrying frontmatter.
- Every tagged topic has a page.
- Every `follows` and `corrects` value is a list naming an existing, earlier report other than this one, and no
  report names one target in both.
- In-repo links in reports, topics, and the index resolve.
- `index.md`, every topic's generated block, and every report's later-reports block are current.

`check` also warns about a topic page that no report tags, and about a standalone HTML report. A warning does not fail
the check.

Only git-tracked files count, and that includes staged files. A report another session has not added yet never
appears in your index. The flip side is that you must `git add` your own new report and any new topic page before
running `build`. Otherwise `build` leaves them out, and `check` does not lint them.

`index.md` and the blocks between the generated markers, on topic pages and reports, are output. Never edit them by
hand.

`stale` drives the periodic topic review. That is a model pass that reads each listed topic page and the reports newer
than its `reviewed` date. It then updates the current position or flags contradictions. It reads only new material, so
its cost tracks how much was written since the last pass, not the size of the wiki.

### Configuration

`wiki.json` at the wiki root sets the index heading and the line under it:

```json
{
  "title": "Engineering wiki",
  "intro": "Start here. Topics hold the current position on a subject; reports are the dated evidence behind them."
}
```

Both keys are required. `build` and `check` fail with an error naming the file when either is missing.

## Commit Messages

This section is the repository standard that the precedence rule in `rules/commit-style.md` defers to. A wiki is all
docs, so a type prefix carries no information.

- Write a plain descriptive subject with the first word capitalized: `Add hit-ratio figures to the eviction study`.
- Never use a conventional-commit prefix such as `docs:` or `fix:`.
- A topic prefix is fine when it names the subject area rather than a change type: `caching: close out sizing notes`.
- Commit only the paths your change touched, with `git commit -- <paths>`. Never use `git add -A` or `git commit -a`.
  Another session may have work in progress in the same checkout. Earlier reports whose later-reports block your
  report changed count as touched.

The `commit-msg` hook enforces the subject style. The `pre-commit` hook runs `bin/wiki check`.

## Agent Rules

- Commit by path. Several sessions work in one checkout at once.
- Write a report in this order:
  1. Add frontmatter, and tag existing topics. Create a topic page only when none fits. Name the earlier reports
     this one follows or corrects.
  2. Update the topic's "Current position" and `reviewed` when the finding changes it.
  3. Stage the new files: `git add -- <report> <new topic pages>`. The tool sees only tracked and staged files.
  4. Run `bin/wiki build`.
  5. Commit the report, `index.md`, every touched topic page, and every earlier report whose later-reports block
     changed, together.
- Never hand-edit `index.md`, a topic's generated "Reports" block, or a report's later-reports block.
- Never rewrite another session's committed report. Write a new one and link back.
- To pick up an earlier line of work, read the topic page first, then the reports it links. Do not search history
  first.

## Setup

The templates live in `templates/wiki/` beside this file. To set up a wiki:

1. Copy `bin/wiki`, `.githooks/pre-commit`, `.githooks/commit-msg`, and `wiki.json` into the wiki root. Keep them
   executable.
2. Edit `wiki.json` to name the wiki.
3. Import the wiki profile from the wiki's `CLAUDE.md` with `@~/.claude/coding-standards-current/profiles/wiki.md`.
4. Write the wiki's `README.md`, with its repository-specific rules.
5. Enable the hooks once per clone with `git config core.hooksPath .githooks`. The hooks are tracked, but
   `core.hooksPath` is local config.

`bin/wiki` is a shim. It runs `scripts/wiki.py` from `$CODING_STANDARDS_ROOT` when that is set, and otherwise from
`~/.claude/coding-standards-current`, the link the coding-standards plugin keeps. A wiki that wants stability instead
of tracking the plugin can vendor the tool. Replace the shim with a copy of `wiki.py` at `bin/wiki`, so the hooks and
docs keep working unchanged.
