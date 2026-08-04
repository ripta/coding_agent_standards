# Exported Skills

Skills in this directory are exported to other projects that import this repo (via plugin, `--add-dir`, or `@import`). Each skill lives in its own directory as `<skill-name>/SKILL.md`.

## Machine-local configuration

Skills must stay portable across users and machines, so anything user- or machine-specific (default directories, local paths, personal preferences) does not belong in `SKILL.md`. Instead, skills that need such state read a per-skill JSON preference file:

```
~/.config/coding_agent_standards/<skill-name>.json
```

Conventions:

- One file per skill, named after the skill (e.g., `session-report.json`).
- Flat JSON with descriptive keys, e.g. `{"default_dir": "/abs/path"}`.
- The file is machine-local state: never edit values into the skill itself, never commit the file anywhere.
- Precedence in the skill should be: explicit value in the user's request > preference file > interactively ask the user, then write the preference file (creating `~/.config/coding_agent_standards/` if needed).
- Validate values read from the file (e.g., check that a configured directory still exists) before relying on them; re-ask and rewrite the file when stale.

See `session-report/SKILL.md` for a worked example of this pattern.
