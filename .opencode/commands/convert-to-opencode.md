---
description: Add a claude/ agent, command, or skill to the OpenCode build
---

Convert these items from `claude/` for OpenCode: $ARGUMENTS

Every conversion goes through `bin/build-opencode`. It copies items from
`claude/` into the gitignored `opencode/` directory and rewrites them for
OpenCode. Never edit `opencode/` by hand, because the next build overwrites it.
Do not change files in `claude/` to suit OpenCode. Put every rewrite in the
build script. If a source change would honestly improve the Claude version as
well, ask the user before you make it.

Commits `4ba6496` (the initial build) and `c42e1fc` (/work-queue) are worked
examples. Read `git show c42e1fc` before you start.

## 1. Find the items

If no items were named, list every agent in `claude/agents/`, command in
`claude/commands/`, and skill in `claude/skills/` that is missing from the
`AGENTS`, `COMMANDS`, and `SKILLS` arrays in `bin/build-opencode`. Ask the user
which to convert with the question tool.

For each name, find out what kind it is: `claude/agents/<name>.md`,
`claude/commands/<name>.md`, or `claude/skills/<name>/SKILL.md`. If the name
matches more than one, ask the user which one they mean. If an item is already
in an array, say so and only rebuild and check it (steps 4 and 5).

## 2. Read the source and its dependencies

Read the whole source file. For a skill, also read every file in its directory.
List what it depends on:

- Agents it launches, such as `coding-standards:<agent>` or `subagent_type`.
- Commands or skills it runs or reads, such as `commands/work-on.md`.
- Files it reads through `${CLAUDE_PLUGIN_ROOT}` or `${CLAUDE_SKILL_DIR}`.

If an agent, command, or skill it depends on has not been converted yet, ask
the user whether to convert that one too. Without it, the converted item
breaks in OpenCode. If it reads a file that has a converted copy, point it at
the copy in `$OUT`, the same way /work-queue points at the converted
/work-on.

## 3. Audit for Claude-only behavior

Find every construct that OpenCode does not support or handles differently.
`bin/build-opencode` already handles these for every file:

- Frontmatter: drops `allowed-tools` and `argument-hint`. For agents, drops
  `name`, turns `tools` into `permissions` deny rules, and adds
  `mode: subagent`. Turns `model` aliases into full model IDs. Drops `model`
  from skills.
- Paths: `${CLAUDE_PLUGIN_ROOT}` and `${CLAUDE_SKILL_DIR}` become absolute
  paths.
- Names: `AskUserQuestion` becomes `question`, "Agent tool" becomes "subagent
  tool", and `coding-standards:` becomes `coding-standards/`.
- In skills, `$ARGUMENTS` becomes a phrase pointing at the user's request,
  because OpenCode skills take no arguments. OpenCode commands do expand
  `$ARGUMENTS` and `$1`, `$2`, and so on, so leave those as they are in
  commands.

Look for these, which still need a rewrite:

| Claude construct | OpenCode handling |
| --- | --- |
| `EnterPlanMode` / `ExitPlanMode` | No plan mode tool. Plan first and hold edits until the user approves the plan with the question tool. See the /work-on and /work-queue rewrites. |
| `SendMessage` to a running agent | Call the subagent tool again with that agent's `sessionID`. |
| `<!-- Workaround for bugs/... -->` | If the bug is in Claude Code, remove the workaround and its comment. |
| `WebFetch` / `WebSearch` | `webfetch` / `websearch` |
| `TodoWrite` / task tools | No equivalent. Ask for a checklist in the reply instead, or drop the instruction. |
| `Monitor` / `run_in_background` | The shell tool with `background: true`. |
| `Skill tool` | The `skill` tool, which takes the skill ID. |
| `@path` in a command | Not expanded in OpenCode command templates. Tell the agent to read the file. |
| `` !`cmd` `` in a skill | Only commands expand it. In a skill, tell the agent to run the command. |
| Hooks, mods, statusline | No equivalent without an OpenCode plugin. Stop and ask the user. |
| "Claude Code" behavior in prose | Rewrite it if OpenCode behaves differently. Leave it if it only names the tool. |

Check anything that is not covered here against the OpenCode V2 docs. Load the
`opencode` skill for the docs index. Do not guess.

If a construct cannot be translated without losing what the item is for,
stop. Tell the user the problem and ask whether to drop the item, cut it down,
or keep it Claude-only.

## 4. Update the build script

Edit `bin/build-opencode`:

1. Add each item to its array. Keep `SKILLS` alphabetical.
2. Put a rewrite in `convert_body` if it applies to any file. Otherwise add a
   `perl -0pi -e` block for that file after the copy loops, next to the
   /work-on and /work-queue blocks. Start it with a short comment saying why
   OpenCode needs the change. Anchor each match on enough source text that it
   fails loudly, not silently, when the source changes.
3. Add every new Claude-only token to the `leftovers` grep, so a future source
   edit that brings one back fails the build.

## 5. Build and check

Run `bin/build-opencode` and fix it until it exits cleanly. Then, for each
item:

1. Run `diff -u` between the source and the generated copy. Confirm that every
   change was on purpose and that the rewritten text reads naturally.
2. Confirm that every absolute path in the generated copy exists.
3. Confirm that the frontmatter matches the OpenCode V2 field list for its
   kind: agents, commands, or skills.

Do not run `bin/build-opencode --link`. Once the global config is set up, new
items show up after a rebuild: it links `opencode/agents` and
`opencode/commands`, and lists `opencode/skills` under `skills`. If
`~/.config/opencode` is not set up that way, tell the user. Do not change it.

## 6. Report

Do not commit. Report:

- Which items were converted, plus any dependencies converted with them.
- Each rewrite that goes beyond the standard ones, and the reason for it.
- Anything that was dropped or cut down in the translation.
- A suggested commit message in the repo's style, such as
  `Translate /work-queue for OpenCode`.
