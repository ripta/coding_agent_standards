# Exported Skills

Skills in this directory are exported to other projects that import this repo (via plugin, `--add-dir`, or `@import`).
Each skill lives in its own directory as `<skill-name>/SKILL.md`.

## Question flow

A skill gets one question checkpoint. Structure the workflow so every question lands in a single `AskUserQuestion` call,
before the skill produces anything.

- Put detection in its own first step. Read the repo, run the commands, check the preference file. Name the step so it
  is obvious that no question belongs in it.
- Follow it with an "ask once" step. Every question the skill needs goes in that one call. Skip the ones detection or
  the user's request already answered.
- A later approval checkpoint is fine. Presenting a draft or a plan and waiting for a yes is a review gate, not a second
  question round.
- Never scatter questions across steps. A skill that asks in step 2, works, then asks again in step 4 has spent the
  user's attention twice for one task.
- When a value is a true prerequisite for detection itself, get it alone and first, then detect, then ask everything
  else in one call.

`cloudbuild/SKILL.md` is the worked example: "Step 1: Detect, without asking", then "Step 2: Ask once, up front".

The exception is a skill whose value is the back-and-forth itself. `proposal-reviewer` resolves design questions one at
a time, and that pacing is the product. Frontload its entry gates -- which document, which mode, where to start -- then
let the loop run. Record the exception in that skill's Rules section, so a later edit does not mistake it for a flaw.

## Machine-local configuration

Skills must stay portable across users and machines, so anything user- or machine-specific (default directories, local
paths, personal preferences) does not belong in `SKILL.md`. Instead, skills that need such state read a per-skill JSON
preference file:

```text
~/.config/coding_agent_standards/<skill-name>.json
```

Conventions:

- One file per skill, named after the skill (e.g., `session-report.json`).
- Flat JSON with descriptive keys, e.g. `{"default_dir": "/abs/path"}`.
- The file is machine-local state: never edit values into the skill itself, never commit the file anywhere.
- Precedence in the skill should be: explicit value in the user's request > preference file > interactively ask the
  user, then write the preference file (creating `~/.config/coding_agent_standards/` if needed).
- Validate values read from the file (e.g., check that a configured directory still exists) before relying on them;
  re-ask and rewrite the file when stale.

See `session-report/SKILL.md` for a worked example of this pattern.
