---
name: rca
description: |
  Root cause analysis from a set of symptoms. Builds hypotheses, tests each
  one against evidence, narrows to the likely causes, then asks "why" down
  each cause until the chain stops. Every link carries its evidence and a
  marker for its confidence. Triggers: "root cause", "rca", "why did this
  happen", "why does this keep happening", "find the cause of", "five whys",
  "postmortem analysis". DO NOT trigger on: a single stack trace with an
  obvious fix, a CI failure (use debug-ci), a code review, or a request to
  write the postmortem document itself (use session-report after this skill).
model: opus
allowed-tools: Read, Glob, Grep, Bash, Agent, AskUserQuestion
---

# Root cause analysis

You find out why something happened. The output is a tree of causes. Each
link in the tree carries evidence. Each leaf is a candidate root cause with a
confidence marker. You never declare a single winner when the evidence
supports more than one.

The analysis is blameless. Causes are decisions, controls, and systems. A
person's mistake is never a leaf. When a chain reaches a human error, the next
"why" asks what let the error through.

Read-only. You read files, git history, and the output of commands. You never
change state, and you never run a command that could.

## Step 1: Gather, without asking

Do all of this before any question. Most of the problem statement is already
in the request or on disk.

1. Copy every symptom out of the request verbatim. A symptom is an observed
   fact: an error text, a metric, a time, a count, a user report. Quote it.
2. Separate the requester's theories from their observations. A theory goes
   into the hypothesis list in step 4. It never becomes a symptom.
3. Note every time in the request. Build the first draft of the timeline.
4. Read the parts of the repo the symptoms point at. Follow the error text,
   the named component, the named config key.
5. Run `git log --since=<window start> --stat` for the symptom window, plus a
   margin before it. When the request gives no times, use the last 30 days
   and narrow later. List every change that touched a relevant path. Use
   `git blame` on the lines the symptoms name.
6. Note where more evidence would live and whether you can reach it: log
   files in the repo, a dashboard the request links, a command the request
   names.
7. Note what the request already ruled out, and whether it says how.

Report what you found in a few lines before asking anything.

## Step 2: Ask once, up front

Make a single `AskUserQuestion` call. Every question the analysis needs goes
in that one call. Do not ask, analyze, then ask again. Skip any question the
request or step 1 already answered.

Candidates, in priority order:

- The symptom window. When did it start, when did it stop, and is it still
  happening.
- What is not affected. Which hosts, tenants, versions, paths, or users look
  the same but are fine.
- What changed. Deploys, config, data, dependencies, traffic, and anything
  outside the repo.
- Where evidence lives and what you may run. Log paths, query commands,
  dashboards, and any read-only command the user wants you to use.
- When the problem was noticed and when it was mitigated, if the analysis is
  for an incident.

Four questions is the limit. Derive the rest or record them as unknowns.
Gaps that surface after this call become marked unknowns in the tree. They
never trigger a second question round.

## Step 3: State the problem

Write the problem statement before any hypothesis. It has three parts.

The "is / is not" table. One row per dimension: what, where, when, how much,
who. Each cell quotes its source. An empty cell is marked `[unknown]`.

The timeline. Absolute timestamps only, one event per line, each with its
source. Include changes, first symptom, detection, mitigation, and recovery.

The change list. Every change inside or just before the window, with its
commit, author-free description, and the paths it touched. A change outside
the repo gets a line too, with whoever reported it quoted.

The "is not" rows matter as much as the "is" rows. A cause that would also
have broken the unaffected cases is wrong, and the table is how you catch it.

## Step 4: Generate hypotheses

List between three and seven hypotheses. Fewer than three means you anchored
on the requester's theory. Cover these categories before adding more within
any one of them:

- A change in the window broke something.
- Configuration or environment differs from what the code expects.
- Data or input differs from what the code expects.
- A dependency, service, or platform changed or failed.
- Load, timing, or concurrency crossed a threshold.
- A process gap let a known problem through.

For each hypothesis record three things. What it claims. What evidence would
confirm it. What observation would rule it out. A hypothesis with no way to
rule it out is marked `[untestable]` and kept, but it never ranks above a
tested one.

The requester's theory is one hypothesis among the others. It gets the same
treatment.

## Step 5: Verify

Gather the evidence each hypothesis asked for. Read files, run read-only
commands, and read git history. When several hypotheses are independent, you
may verify them in parallel with the Agent tool. Every citation a subagent
returns gets re-read by you before it enters the tree.

Grade every piece of evidence:

| Grade | Meaning |
| --- | --- |
| D | Direct. You observed it or reproduced it yourself. |
| L | Logged. A log line, metric, or command output with a timestamp. |
| S | Secondhand. A person reported it. Quote them. |
| I | Inferred. Follows from other evidence but was not observed. |

Cite evidence the way session-report requires. A file path with line numbers.
A verbatim command and the relevant slice of its output. A log line with its
timestamp. A quoted sentence from the request.

Check timing on every piece. Evidence from outside the symptom window does
not count for or against a hypothesis unless the hypothesis explains why it
should. Mark the mismatch instead of quietly using it.

Sort the hypotheses into four buckets:

- Likely. Confirming evidence present, no ruling-out observation found.
- Possible. Nothing confirms it and nothing rules it out.
- Ruled out. The ruling-out observation was made. Record it with its evidence.
- Untestable. No evidence is reachable from here. Record what would be needed.

Every likely hypothesis continues to step 6. Possible hypotheses are kept and
reported. Ruled-out hypotheses stay in the final output with the evidence
that ruled them out.

## Step 6: Ask why

For each likely hypothesis, ask why it was true. The answer is a cause one
level deeper. Ask again. Each answer is a link in the chain.

Every link records:

- The cause, in one sentence.
- Its evidence, graded and cited as in step 5.
- The checks below, each passed or marked.
- A marker from the legend in step 9.

Run three checks on every link:

1. Precedence. The cause happened before the effect. Compare timestamps.
   Failure marks the link `[time-mismatch]`.
2. Counterfactual. Without this cause, the effect would not have happened.
   If the effect would have happened anyway, the cause is a contributing
   factor, not a link. Move it to the factor list.
3. Sufficiency. This cause alone produces the effect. If it needed a second
   condition, the link is a joint branch. Record both conditions.

Branch when more than one cause fits. Label the kind:

- Alternatives. One of them is true. Keep every alternative until evidence
  splits them. Each alternative continues as its own chain.
- Joint. Both were needed. Each condition continues as its own chain, and the
  link records that remediation must address at least one of them.

Stop a chain when any of these holds:

- The next "why" gives no deeper cause. The answer restates the current link
  or becomes a generality.
- The cause is a decision, control, or design that someone could change.
  This is the leaf you want.
- The cause is outside anyone's control. Vendor behavior, physics, a
  third-party outage. Record it and stop.
- The evidence runs out. Mark the link `[unknown]`, record what evidence
  would extend the chain, and stop. Never speculate past the evidence.

Never stop at a human error. "Someone pushed a bad config" has a deeper why:
what let a bad config reach production without a check.

## Step 7: Detection and recovery

When the analysis is for an incident, run two shorter chains alongside the
failure chains. Why did detection take as long as it did. Why did recovery
take as long as it did. Each follows the same link rules as step 6. Their
leaves are usually contributing factors, not root causes, and the report
labels them that way.

Skip this step when the request is about a defect with no incident timeline.

## Step 8: Check coverage

Before reporting, test the whole tree.

1. Walk every symptom in the "is" rows. Each one must be explained by at least
   one chain. An unexplained symptom means a missing hypothesis. Go back to
   step 4 for it.
2. Walk every "is not" row. No chain may predict a failure there. A chain
   that does is wrong or incomplete. Revisit its links.
3. Read each chain backwards from the leaf, joining links with "therefore".
   A step that does not follow marks a broken link.
4. Revisit the ruled-out list. New evidence from step 6 may revive one. Say
   so when it does.

## Step 9: Report

Render the tree in the reply. Use this shape.

```markdown
## Problem

<is / is not table>
<timeline>
<change list>

## Causes

Symptom: <quoted symptom>
└─ because <cause> [likely] (L): <citation>
   └─ because <cause> [confirmed] (D): <citation>
      ├─ alternative A: <cause> [missing-source]
      │  └─ candidate root cause: <cause> [unknown]. Needs: <evidence that would resolve it>
      └─ alternative B: <cause> [challenged]: <who challenged it, quoted>
         └─ candidate root cause: <cause> [likely] (L): <citation>

Trigger: <the proximate event, cited>
Contributing factors:
- <factor> (D): <citation>

## Detection and recovery
<chains from step 7, or "not applicable">

## Ruled out
- <hypothesis>. Ruled out by <evidence, cited>

## Unknowns
- <link>. Needs: <the data that would resolve it>
```

Marker legend. Use these and no others:

- `[confirmed]` evidence of grade D or L supports it and nothing contradicts.
- `[likely]` evidence supports it but part of it is inferred or secondhand.
- `[possible]` nothing confirms it and nothing rules it out.
- `[inferred]` no direct evidence. Follows from neighboring links.
- `[missing-source]` the claim came without a citation and you could not find
  one.
- `[challenged]` someone disputed it. Quote the dispute.
- `[contradicted]` evidence points the other way. Cite it.
- `[time-mismatch]` the evidence sits outside the symptom window.
- `[unknown]` the chain ends here for lack of evidence.
- `[untestable]` no reachable evidence could decide it.

Every leaf is a candidate root cause. More than one leaf is normal. Rank
them by evidence grade and marker, and say which you would act on first and
why. Never collapse to one leaf unless every other was ruled out.

Close with one line offering to write the analysis to a file through
`/session-report`. Do not write the file yourself.

## Rules

- Blameless. No link names a person as the cause. A human error always gets
  one more "why".
- Read-only. Never run a command that changes state or restarts a service.
  Never write files.
- One question round, in step 2. Gaps found later are marked `[unknown]` in
  the tree, never asked.
- Every link carries a citation. A link with none is marked
  `[missing-source]`, never left bare.
- Evidence from outside the symptom window is marked `[time-mismatch]`, never
  silently used.
- Ruled-out hypotheses stay in the report with the evidence that ruled them
  out.
- Every `[unknown]` names the evidence that would resolve it.
- Subagent findings are re-read before they enter the tree. A citation you
  did not open yourself is `[missing-source]`.
- Never declare a single root cause while another leaf is still `[likely]` or
  `[possible]`.
- Follow `rules/sentence-structure.md` in the report. One idea per sentence.
