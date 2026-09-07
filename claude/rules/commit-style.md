# Commit Style

## Precedence

Repository standards come first. This file is not prescriptive. Determine the
format in this order, and stop at the first one that answers:

1. An explicit standards document in the repository -- `CONTRIBUTING.md`, a
   commit convention doc, or the project's own `CLAUDE.md`
2. The repository's history, when no such document exists. Read
   `git log --format='%s'` and match the observed subject style
3. The defaults below

History is a repository standard, not a fallback for a missing one. A repo whose
subjects are capitalized sentences with no scope prefix is already following its
own convention. Match it.

Read the history before writing the first commit in an unfamiliar repo.

Precedence governs the subject format and structure. The Body and Forbidden
Openers sections below are writing-voice rules. They hold regardless of which
subject format the repository uses.

## Defaults

Apply these only when the repository expresses no convention of its own.

- Format: `scope: description` (e.g., `auth: handle expired tokens`)
- Keep the subject line under 72 characters
- Use imperative mood: "add feature" not "added feature"

## Body

- Include a body only when it adds information the subject does not carry
- For trivial changes -- docs tweaks, mechanical updates, one-line fixes -- stop
  at the subject. A body that restates the subject is noise
- The body explains WHY, not WHAT. The diff shows the what
- Describe the problem being solved and the observable behavior change
- Do not reference phase, milestone, or proposal numbers. Those are project
  management artifacts
- Avoid class names, struct names, and other implementation nouns
- Avoid over-explaining. Keep it succinct

## Forbidden Openers

Never open a subject line or a body with a recap of the prior state. Lead with
the reason for the change, or with what the change enables.

These openers are forbidden:

- "Previously, ..."
- "X was Y"
- "X can't / couldn't do Y"
- "Operators had to ..."
- "The system required ..."

The ban covers any framing that narrates the world before the change, in past or
present tense. It applies to subject lines as much as bodies. A subject like
"Operators running on remote hosts could not ..." is forbidden.
