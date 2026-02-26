# Writing Style Profile

This document characterizes the author's writing voice as observed in commit messages
and code comments across personal projects. It is descriptive, not
prescriptive — a reference for what the voice sounds like, not a set of rules to follow.
For formatting rules, see `claude/rules/commit-style.md`.

## Commit Messages

### Scoping

Multi-package projects consistently use a `scope: description` format, where the scope
maps to a package path or project artifact: `pkg/enrichment:`, `cmd/redirector:`, `db:`,
`ui:`, `model:`, `goreleaser:`, `Makefile:`. Single-package projects tend toward unscoped
subjects that describe the change directly.

### Tone spectrum

Commit subjects range widely in register. Technical commits are precise and detailed:

> `Fix scheduler deadlock detection for channel-blocked tasks`
> `Enforce block entry alignment when formatting source code`

Others are terse, sometimes a single word:

> `More filters`
> `Tweaks`
> `forgot this one`

And some are openly frustrated, humorous, or candid:

> `ui: god, the filters are fucking broken`
> `ui: istg this keeps breaking`
> `cmd/redirector: stop being so honest in error messages`
> `Fix double poop bug in native load`
> `will i regret this?`

The register tracks the emotional context of the work, not a fixed persona.

### Bodies explain "why"

When commit bodies appear, they describe the problem and how the fix addresses it. The
language is conversational but technically precise — a scheduler fix opens with "The
scheduler's runLoop break condition only checked for sleepers and IO waiters," and a
coroutine rewrite notes "We don't need to reparse, which means no reexecution (and no
doubling of side-effects), and no gnarly error threading."

Bodies sometimes include asides that reveal the author's uncertainty or relief:

> No tests seem broken, so hopefully I didn't break anything.
> It's getting real difficult to debug hanging tests, and this hopefully gives me more info.
> Unfortunately, a bit odd to place it next to ratios due to its dependence on ratio conversions.

Bundled changes use numbered lists:

> 1. Transitive module dependency resolution...
> 2. Source module preservation...
> 3. Native word capture in modules...

### Capitalization and evolution

The default is lowercase subjects. Older commits sometimes use title case (`Structfiles
Improvements`, `Placeholder Text Generator`, `Spruce Up Search`), reflecting an evolved
convention rather than inconsistency.

### Markers

Exploratory work uses an `Experiment:` prefix (`Experiment: Custom pragma definition and
querying`). Refactoring gets a `Refactor:` prefix (`Refactor: Decompose
executeInstructions into smaller functions`). A `See-Also:` trailer occasionally links
to external references in the body.

## Code Comments

### Doc comments

Doc comments follow standard convention for the language: the exported identifier name
leads the sentence, and the description is concise and functional. The author does not
over-document — comments appear on types, constructors, and non-obvious public methods,
not on every exported symbol. Some doc comments include domain-specific notation:
`/// send ( val ch -- )`, `/// try-receive ( ch -- val/f flag )`.

### Inline comments

Inline comments are narrowly focused on the non-obvious. They explain *why*, not *what*.
Many are short declarative fragments:

> `// noop`
> `// alphabetical`
> `// for testing`
> `// Log but don't fail`
> `// Both empty = identical`

### Numbered algorithm steps

Multi-step logic is annotated with numbered comments that read like an outline:

> `// 1. External ID (GUID vs Link)`
> `// 2. Published date fallback chain`
> `// 3. Content/description truncation`

This pattern appears across projects regardless of language.

### Attributed annotations

Personal annotations use an attributed format: `TODO(ripta):`, `NOTE(ripta):`,
`XXX(ripta):`. Universal concerns use bare tags: `NOTE:`, `SECURITY WARNING:`, `FIXME:`.
`XXX` annotations often carry editorial commentary:

> `// XXX(ripta): omg, ew`
> `// XXX(ripta): Module cache hit - side-effects won't run again. Is this okay? It better be.`
> `// XXX(ripta): Hack to set import target frame... No rugrats for now.`
> `// XXX(ripta): Not a fan of reparsing lines here. Find better ways in the future.`

### External references

Comments link to RFCs, Unicode code points, Wikipedia articles, and GitHub URLs when the
code implements or relates to an external specification:

> `// Canadian Aboriginal Syllabics... See: https://en.wikipedia.org/wiki/Canadian_Aboriginal_Syllabics`
> `// Variation selectors 1-16 https://unicode.org/charts/nameslist/n_FE00.html`

Mathematical notation appears inline: `// log2(10) ~ 3.32193`, `// scale = 2^(-precision)`,
`// J(A,B) = |A ∩ B| / |A ∪ B|`.

## Voice and Tone

### Register fluidity

Formality is context-dependent, not personality-fixed. A scheduler doc comment is precise
and structured; a debugging commit subject can be profane. The author does not maintain a
uniform register — the writing shifts to match the situation, from careful technical
exposition to `ui: filter fix take 84`.

### Directness

The author states facts and opinions plainly, without hedging. A commit body says "The
scheduler's runLoop break condition only checked for sleepers and IO watchers" rather than
"It seems like the break condition might not be checking for all cases." Rhetorical
questions are used to make a point, not to equivocate: "Can you imagine overriding `dup`
to return the same constant?"

### Humor and candor

Humor appears in service of honesty. Frustration is expressed directly (`istg this keeps
breaking`, `filter fix take 84`, the `:(` emoticon on an API integration commit). Self-awareness
surfaces as mild self-deprecation (`whoops!`, `forgot this one`, `Adds tests lol`). There
is no affectation — the humor reads as a person talking to themselves in the commit log.

### Technical precision amid informality

Even in casual contexts, the author uses correct technical vocabulary. RFC numbers are
cited by number. Unicode code points are referenced precisely (`U+1D455`, `U+210E`).
Diacritical marks appear where etymologically correct: `coöperative`, `reëxport`,
`reïmplement`. Foreign phrases retain their marks: `à la`. Set notation and mathematical
formulas are written inline in comments. The informality is in register, not in rigor.

## Vocabulary and Phrasing

The author favors specific, vivid verbs over generic ones: "pluck" for extraction
(`pluck page titles from the wikipedia link as a fallback`), "bail out" for early exit
(`bail out on context cancellation instead of processing everything`), "wire up" for
integration (`Wire up --trace-modules flag`), "first stab" for initial attempts.

Domain-specific terms are coined when they clarify a distinction: "stopping error" versus
"skippable error" for two severity levels in a processing pipeline. A change is
"defensively" limiting something, or "spruc[ing] up" a feature, or noting something is
"long-overdue."

Semicolons connect related clauses. Em dashes appear in commit bodies for
interruptions or restatements. Underscores mark emphasis in commit messages
where markdown rendering is available: `_ignores_ all HTML instead of skipping
_additional_ processing`.

Capitalization defaults to lowercase. ALL CAPS is reserved for warning-level annotations
(`SECURITY WARNING:`, `NOTE:`). Older commits occasionally use title case for merge or
PR titles.
