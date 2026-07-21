# Response Style

Applies to conversational responses in chat. For written artifacts, see
`sentence-structure.md`, `writing-voice.md`, `commit-style.md`, and
`pr-style.md` instead.

- Lead with the answer. Avoid narrating a plan before giving it. If the answer
  is a sequence of steps, give the steps as a numbered list, not a description
  of the plan.
- Use concrete units instead of vague terms: a duration ("30 minutes"), a
  count ("12 rows"), or a command, instead of "a while," "some," or
  "iteration."
- State facts plainly. Avoid hedging a known problem behind an implication.
  Say "The `users` table is missing `last_login_at`. Run `ALTER TABLE users
  ADD COLUMN last_login_at TIMESTAMPTZ`" instead of "We may need to alter the
  schema to address this."
- Avoid opening with affirmations, such as "Great question," "Let me first,"
  "Looking at your code," "To answer your question."

Exception: when the user asks to explain, walk through, or sketch something,
narrate normally. These rules govern the default terse mode, not requested
exposition.
