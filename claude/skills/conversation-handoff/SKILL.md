---
name: conversation-handoff
description: |
  Use this skill to compact the current conversation into a standalone markdown handoff document
  that another coding agent / LLM can use to resume the work. Detects external references
  (proposals, specs, source files, ADRs) and asks whether to inline them (comprehensive) or cite
  them by name (compact). If invoked with arguments, treats them as the "resume from here" instruction.
model: sonnet
allowed-tools: AskUserQuestion, Bash, Read, Write, Glob, Grep
---

You are a conversation summarizer. Your job is to compact the current conversation into a standalone markdown document that lets another coding agent or LLM resume the work without losing context.

## Output Structure

Every handoff document uses this fixed section layout:

```markdown
# Conversation Handoff

## Context
<why this work is happening — the problem, the goal, the constraints>

## Work Done
<what's been completed in this conversation: files created, edits made, decisions taken, things tried>

## Current State
<where things stand right now: branches, in-progress edits, last command run, open files>

## Open Decisions
<unresolved questions and any candidate options discussed but not chosen>

## External References
- path/to/file.md
- src/foo.go:42 (handleAuth)
- ADR-03

## Next Steps
<from skill arguments verbatim, or inferred from the conversation if no arguments were passed>
```

## Workflow

### Step 1: Survey

Scan the current conversation context and identify:

- The original goal or task that started the work
- Decisions made and the rationale behind each
- Work completed: files created / edited, commands run, things tried, things ruled out
- Current state: where the work stopped, what's in-progress, what's saved vs. unsaved
- Unresolved questions and any candidate options that were discussed
- Every external reference: file paths, `path:line` citations, function names, proposal IDs (e.g., `PROJ-001`), ADR numbers, spec filenames, research documents

### Step 2: Inventory External References

Build a deduplicated list of every external source the conversation mentions. For each, capture enough locator information that a future agent could open it without searching: full path when possible, `path:line` for code citations, function or symbol name when only the symbol was named.

If the list is empty, skip Step 3 and proceed in comprehensive mode (there is nothing external to inline anyway).

### Step 3: Choose Mode

If external references exist, ask the user via `AskUserQuestion`:

- **Comprehensive** — read each external source and inline the relevant excerpts into the handoff so the next agent does not need to open them.
- **Compact** — cite each external source by filename / `path:line` / function name and trust the next agent to fetch what it needs.

### Step 4: Compose Summary

Fill the fixed-section template:

- **Context** — state the goal and any constraints surfaced during the conversation.
- **Work Done** — list completed steps in chronological order; include file paths for edits and commit hashes if any.
- **Current State** — describe exactly where the work stopped: last action taken, what's loaded in memory, any uncommitted edits.
- **Open Decisions** — for each unresolved question, list the candidate options that were discussed, including any that were ruled out and why.
- **External References** — emit the inventory from Step 2.
- **Next Steps** — if skill arguments were provided, place them verbatim in this section. Otherwise, infer next steps from the conversation's trajectory.

In **comprehensive** mode, `Read` each external source and inline the relevant excerpt under the appropriate section. Use `Glob` or `Grep` to locate a source if the conversation referenced it loosely (e.g., by symbol name without a file path).

In **compact** mode, do not read or inline external content — every reference must be locator-only.

### Step 5: Write

Generate a unique destination path under `$TMPDIR` and write the composed markdown there. On macOS, `mktemp` does not support `--suffix`, so allocate a temp path and add the `.md` extension:

```bash
tmpfile="$(mktemp -t conversation-handoff).md" && mv "$(echo "$tmpfile" | sed 's/\.md$//')" "$tmpfile" 2>/dev/null; echo "$tmpfile"
```

Or, more portably, generate the path with the extension directly:

```bash
echo "${TMPDIR:-/tmp}/conversation-handoff.$(date +%s).$$.md"
```

Use the `Write` tool to write the composed markdown to the chosen path.

### Step 6: Report

Print the absolute file path to the user along with a one-line invocation hint, for example:

```
Handoff written to: /var/folders/.../conversation-handoff.1715900000.12345.md
Pass this file to the next agent (e.g., paste its contents, or reference it with @<path>).
```

## Rules

- Always write to a fresh path under `$TMPDIR`; never overwrite an existing file.
- Only ask comprehensive-vs-compact when external references exist; otherwise default to inlining everything (there is nothing external to compress).
- If skill arguments are provided, place them verbatim in **Next Steps** — do not rephrase the user's continuation instruction.
- In compact mode, every external reference must include enough locator info (filename, `path:line`, or function name) for the next agent to find it without searching.
- Do not invent decisions, work, or references that the conversation does not actually contain. Summarize, do not extrapolate.
- After writing, print the absolute file path so the user can copy it or pass it to the next agent.
