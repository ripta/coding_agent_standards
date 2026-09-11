---
name: walkthrough
description: |
  Use this skill to produce a self-contained interactive HTML page that explains a
  concept, feature, changeset, commit, diff, branch, or PR. It gathers evidence from
  the repo, verifies every claim with fast subagents, then writes one static HTML file
  with diagrams, annotated code, interactive figures, and a sequestered beginner
  background track. Triggers: "explain this PR/commit/branch", "build a walkthrough of
  X", "make an explainer page for X", "write up how X works as a page". DO NOT trigger
  for a plain chat explanation, a README, ARCHITECTURE.md, a commit message, or a code
  review.
model: opus
allowed-tools: Agent, AskUserQuestion, Bash, Read, Write, Edit, Glob, Grep, WebSearch, WebFetch
---

You build one interactive HTML page that explains a target to a reader who is
not you. The page must survive being uploaded to a plain static file server.
One file, no build step, no local assets.

You act as an **orchestrator**. Subagents gather the evidence and check your
claims. You do the synthesis and write the page, because the page's value is
the framing and that does not delegate well.

The goal is **intuition, not coverage**. A reader should leave knowing why the
change exists and what mental model makes it obvious. Completeness belongs in
the links you provide, not on the page.

## Bundled files

Read these before writing any HTML. They live in this skill's directory
(`${CLAUDE_SKILL_DIR}`, or beside this file if that variable is unset).

- `template.html` — the page scaffold. Design tokens for both themes, the theme
  toggle, tabs, callouts, code markers, and the CDN loads. Start every page
  from a copy of it.
- `components.md` — the diagram families and the interactive-element catalog,
  with copy-paste snippets. Pick from here before inventing a widget.
- `check.py` — mechanical self-containment and link checks. Run it before the
  review.

## Workflow

### Step 1: Resolve the target

The argument is a concept, a feature, a changeset, a commit, a diff, a branch,
or a PR. Classify it, then resolve it to concrete evidence. All git use is
**read-only** — never check out, switch, branch, worktree, push, or pull.

| Argument looks like | Resolve with |
| --- | --- |
| `#123`, `PR 123`, a GitHub PR URL | `gh pr view <n> --json title,body,url,author,headRefName,baseRefName,commits`, then `gh pr diff <n>` |
| A hex sha, `HEAD`, `HEAD~3`, a tag | `git show --stat <ref>`, then `git show <ref>` |
| `a..b`, `a...b` | `git diff <range>` and `git log --oneline <range>` |
| Nothing, "my changes", "working tree" | `git status --short` and `git diff HEAD` |
| A branch `git rev-parse --verify` resolves | `git merge-base <default> <branch>`, then `git diff <base>...<branch>` and `git log --oneline <base>..<branch>` |
| Anything else | A feature or concept — locate it in the repo by search |

Find the default branch with `git symbolic-ref --quiet
refs/remotes/origin/HEAD`, falling back to `main` then `master`. If `gh` is
missing or unauthenticated, say so and ask how to proceed. Do not fetch or
mutate the repo to work around it.

A **feature** names a capability that exists in the code. Find its entry
points, its tests, and the commits that introduced it (`git log -S` on a
distinctive identifier). A **concept** may be repo-specific or general. Decide
which. If the repo implements it, ground the page in that implementation. If
not, the page is conceptual and its examples are yours to invent.

Ask the user only when resolution is genuinely ambiguous — a name matching both
a branch and a directory, or a concept that could mean two different
subsystems. One round of questions, then proceed.

### Step 2: Resolve the output path

Preference file: `~/.config/coding_agent_standards/walkthrough.json`, shape
`{"default_dir": "/abs/path"}`. It is machine-local state. Never edit it into
this skill and never commit it.

Precedence:

1. A path in the user's request → use it for this page only. Do not update the
   preference file unless the user says to make it the default.
2. Otherwise `default_dir` from the preference file.
3. If the file is missing, or `default_dir` no longer exists, ask the user for
   a directory, verify it, then write the preference file. Create
   `~/.config/coding_agent_standards/` if needed.

Filename: `YYYYMMDD-<slug>.html`, today's date, kebab-case slug naming the
subject. Name the subject, not the activity —
`20260911-retry-budget-rewrite.html`, not `20260911-explaining-a-pr.html`. On a
filename collision, extend the slug. Never overwrite an existing page.

### Step 3: Gather evidence

Read the primary diff, or the primary implementation file, yourself. That is
the artifact you are explaining. A summary of it is not good enough.

Fan the rest out to parallel `Explore` subagents. **Issue all the Agent calls
in one message.** Cap the fan-out at six. Give each the same brief, then its
own beat:

> You are gathering raw material for one section of an explainer page about
> `<target>`. This is strictly read-only — do not modify any file. Your
> deliverable is evidence, not prose. For every claim, return the exact
> `file:line` plus a verbatim snippet of a few lines proving it. Paths must be
> relative to the repository root. Prefer reading code over docs when they
> disagree. Mark anything you are inferring as a guess. Be thorough within your
> beat and ignore the rest.

The beats, adapted to the target:

- **Before** — how the code worked prior to the change. This is what makes the
  change legible. For a concept or feature, this is the problem it solves.
- **Blast radius** — every caller, subclass, test, and config touched by or
  depending on the changed surface.
- **Background** — the abstractions a newcomer needs before the change makes
  sense. Name the types, the invariants, and the vocabulary. This feeds the
  beginner track.
- **Supporting documents** — READMEs, ADRs, design docs, proposals
  (`spec/proposals/` and similar), the commit or PR body, linked issues. Return
  titles and paths.
- **History** — `git log` on the touched files, prior attempts, reverts, and
  the commits that set this one up.
- **External** — when the target leans on a library, protocol, or published
  algorithm, fetch the upstream documentation. Use `WebSearch` and `WebFetch`.

Also establish the link base. If `git remote get-url origin` is a GitHub
remote, build permalinks pinned to the resolved sha:
`https://github.com/<owner>/<repo>/blob/<sha>/<path>#L42-L58`. Pinning to a sha
keeps the links correct after the branch moves. With no usable remote, cite
repo-relative paths as plain text instead of broken links.

### Step 4: Verify every claim

Write out every factual claim the page will make as a numbered ledger. A claim
is anything a reader could check: a line number, a function's behavior, a
default value, an ordering, a performance characteristic, a quotation from a
doc.

Dispatch verifier subagents with `model: haiku`. This is mechanical work and
the fast model is the right tool. Batch ten to fifteen claims per verifier and
run them in parallel. Brief them:

> For each claim, open the cited file and check it. Return one verdict per
> claim: `CONFIRMED`; `CORRECTED` with the right line number when the content
> is there but the line drifted; or `REFUTED` when the cited content is not in
> the file. Quote the line you found. Do not fix, improve, or editorialize on
> the claims — only check them.

Then:

- `CONFIRMED` and `CORRECTED` claims go on the page, with the corrected line.
- `REFUTED` claims come off the page. Do not soften them into hedged prose.
  Either re-derive the claim from source yourself and re-verify, or drop it.
- A claim left unverified because a subagent died counts as refuted.

Three categories bypass code verification, and each has its own bar:

- **External claims** — verify against the fetched document, not from memory.
- **Intuition, analogy, and framing** — authorial. They need no verification.
  They must be recognizable as your framing rather than as fact.
- **Mock data** — invented examples for figures. Label them as illustrative.
  Never present fabricated numbers as measurements.

### Step 5: Plan the page

Decide, then report the plan to the user in a few lines before writing. This is
a checkpoint, not a gate — proceed unless the user objects.

**The spine.** One sentence naming the essential idea. Everything on the page
either serves that sentence or is cut. Then the arc: the problem, the old
model, the pivot, the new model, the consequences.

**The tabs.** The template ships four. Rename or drop them to fit.

- *Essentials* — the spine, the key diagram, the intuition. Five minutes.
- *Background* — the beginner track, sequestered here so it never interrupts
  the main line. Assume nothing. Define the vocabulary, the types, and the
  surrounding system.
- *Code tour* — the high-level walkthrough, grouped by idea.
- *Deep dive* — edge cases, alternatives considered, and the links out.

**The diagrams.** Pick two or three families from `components.md` and reuse
them for the whole page. A page with six diagram styles reads as six pages. Put
sample data on the edges of any data-flow diagram. A concrete payload beats a
labeled arrow.

**The interactions.** Pick from the catalog in `components.md`. Two or three
well-chosen widgets beat a page of gadgets. Every interaction must teach
something a static figure cannot.

**The code groups.** Group the changes by the idea they serve, not by file and
not by the order they appear in the diff. Three to five groups, each with a
one-line heading that states what the group accomplishes. Say which files each
group touches and link them. Splitting one file across two groups is correct
when the file does two things.

### Step 6: Write the HTML

Start from a copy of `template.html`. Extend its CSS rather than fighting it.

Hard constraints:

- **One file.** No local stylesheet, script, image, or font. Inline SVG for
  figures you author. Data URIs only for tiny icons.
- **No build step.** Plain HTML, CSS, and JS that a browser runs as-is. No JSX,
  no TypeScript, no bundler syntax, no ES module imports of local paths.
- **CDN only for libraries**, over `https`, from cdnjs or jsDelivr. Pin an
  exact version. Never `latest` or `@next`. The template already loads Mermaid,
  D3, and Chart.js — delete the ones the page does not use.
- **Theme toggle.** System preference by default, a visible toggle, the choice
  persisted in `localStorage`. The template implements this. Keep its hooks
  intact.

Theme gotchas the template already handles, which you must not break:

- Mermaid bakes its colors in at render time. A theme switch means restoring
  each diagram's source and running Mermaid again. The template stores the
  source and provides the re-render hook.
- Chart.js reads its colors once. The template keeps a chart registry and
  re-applies colors from the CSS custom properties on toggle. Pass every chart
  you create through `registerChart`.
- D3 and hand-authored SVG should use `fill: var(--accent)` and friends rather
  than literal colors. Then theming is free.

Content rules:

- **Lead with intuition.** Give the reader the mental model before the
  mechanism. A concrete example with mock data beats an abstract description.
- **Use `<pre>` for code.** Hand-color with the CSS classes in the template. Do
  not load a syntax-highlighting library for a few lines. Never paste a whole
  file. Show the lines that carry the idea and link to the rest.
- **Mark up long code blocks with numbered markers** (`.mk` in the template)
  rather than line numbers. A circled ② in the gutter is easier to find than
  "line 47". Wire each marker to its note; the template's marker JS does this.
- **Use callouts** for definitions, key concepts, intuition, edge cases,
  warnings, and further reading. The template styles all six. Do not put
  ordinary prose in a callout — a page of boxes has no emphasis left.
- **Link everything.** Every claim about code links to the source. Every
  referenced doc, ADR, proposal, issue, and PR is linked by title. External
  links get `target="_blank" rel="noopener noreferrer"`.
- **Prose is short.** One idea per sentence. Split a sentence doing two jobs
  into two sentences. Prefer the plain concrete statement over the qualified
  one. Cut every word that earns nothing.
- **No ASCII diagrams.** Ever. Use Mermaid, inline SVG, or styled HTML.

If the page needs a plotted chart and a `dataviz` skill is available in the
session, read it before choosing chart colors.

### Step 7: Check, then review

Run the mechanical check first. It is deterministic and catches what a reader
cannot:

```sh
python3 "${CLAUDE_SKILL_DIR}/check.py" <path to the written page>
```

Fix every error it reports. Judge the warnings and fix the ones that matter.

Then spawn one `general-purpose` reviewer with `model: sonnet`. Fast is the
point — this is a readability pass, not a security audit. Brief it:

> Review the HTML explainer page at `<path>` for usability and content. Read
> the file. Do not edit it. Report findings ranked most-important first, each
> with the approximate line and a concrete fix.
>
> Usability: does the page work as a single static file, with no build step and
> no local assets? Does the theme toggle cover every element, including
> diagrams and charts? Is the beginner material genuinely sequestered, so an
> expert can skip it and a beginner can find it? Do the interactive elements
> teach something, and do they degrade sanely if a CDN fails? Is the tab and
> heading structure navigable? Are the code markers wired to their notes?
>
> Content: does the page lead with intuition rather than mechanism? Is the
> spine — the one essential idea — stated plainly and early? Are the code
> groups organized by idea? Is invented example data labelled as illustrative?
> Are there links for digging deeper? Is the prose concise, one idea per
> sentence?
>
> Flag anything that reads as filler, any claim with no link behind it, and any
> diagram that would be clearer as prose.

Apply the findings. Re-run `check.py` if you changed structure. Spawn a second
reviewer only if the first found structural problems.

### Step 8: Report

Give the user the absolute path, the resolved target, the page's spine in one
sentence, the tab and section outline, the claim tally (confirmed, corrected,
dropped), and anything you could not verify or resolve. If the output directory
is a git repo, do not commit or push unless asked.

## Rules

- Read-only everywhere except the one HTML file you write, and the preference
  file when the user sets a default directory. Never check out, switch, branch,
  worktree, push, or pull. Brief every subagent as read-only.
- Resolve the target in Step 1 before gathering anything. Ask at most one round
  of questions, and only when resolution is genuinely ambiguous.
- Every factual claim on the page is verified by a `haiku` subagent against the
  cited source before it ships. Refuted claims come off the page. They are
  never softened into hedged prose.
- Intuition, analogy, and invented example data are allowed and valuable. Label
  them as such. Never present fabricated numbers as measurements.
- The page is one self-contained HTML file: no build step, no local assets, CDN
  libraries only, at pinned versions over https. It must work when uploaded to
  a plain static file server.
- Every page has a theme toggle that defaults to the system preference and
  persists the choice. Diagrams and charts re-theme with the page.
- Beginner background is sequestered into its own tab or into collapsed
  sections. It is never interleaved with the main line.
- Group code changes by the idea they serve, not by file order in the diff.
- Pick two or three diagram families and reuse them across the page. No ASCII
  diagrams.
- Run `check.py` and then a `sonnet` reviewer before reporting. Apply what they
  find.
- Never overwrite an existing page. Extend the slug on collision.
