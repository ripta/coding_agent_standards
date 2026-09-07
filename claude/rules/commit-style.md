# Commit Style

- Format: `scope: description` (e.g., `auth: handle expired tokens`)
- Keep the subject line under 72 characters
- Use imperative mood: "add feature" not "added feature"
- Projects may override this with local commit message standards

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
