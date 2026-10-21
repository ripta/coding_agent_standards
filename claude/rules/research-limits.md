# Research Limits

Multi-agent research skills, such as `deep-research`, start parallel subagents.
Each one runs its own searches. Keep that spend bounded unless the user lifts
these limits for a given request.

- Start at most 2 research subagents per request.
- Skip any optional second round of research. Write the report from the first
  round, and list what it could not answer as gaps.
- Use a single report-writer subagent, as the skill asks.
- Never start research subagents from the Workflow tool.
- When a question needs only a few facts, search directly instead of invoking
  a research skill.
- These skills write notes and reports into the working directory. If the user
  has not named an output location, ask via AskUserQuestion before writing
  into a project tree.

A limit the user states in the request overrides these defaults.
