---
description: Iterate a design question with the design critic until it converges, then ask
argument-hint: "[design question or description] [proposal path]"
model: opus
allowed-tools: Agent, AskUserQuestion, Bash, Read, Glob, Grep, WebSearch, WebFetch
---

Converge on a recommendation for the design question in $ARGUMENTS, then let
the user decide. Use this for a design choice that has no proposal yet, such as
one that comes up in plan mode or in conversation. For open questions in a
proposal, use `proposal-reviewer` instead.

The protocol lives in
`${CLAUDE_PLUGIN_ROOT}/project-management/design-convergence.md`. The ranking
it relies on lives in the "Choosing Options" section of
`${CLAUDE_PLUGIN_ROOT}/rules/decision-making.md`. Read both now. If either
cannot be read, stop and tell the user the standards are not available.

1. **Frame the question.** Take the question from the arguments. When they
   are empty or point at the conversation, such as "this" or "the design
   above", take it from the design under discussion. Do not search for a
   proposal. Treat a path in the arguments as the proposal the question
   belongs to, and assume no proposal without one. From the conversation:
   - Decisions the user already made are fixed constraints, not open
     questions.
   - Options already raised go on the list with the ones you research.
   Before running, state each question you will run in one line, so a wrong
   reading shows up before the first pass. Read the code the design touches.
   Ask only when neither the arguments nor the conversation say what is being
   decided.
2. **Build the options.** Research them by "Choosing Options". The complete
   option is always on the list.
3. **Run the loop.** Follow `design-convergence.md`. When the question has no
   proposal, give the critic and the judge a description of the design in
   place of a proposal path: the context, the constraints you found in the
   code and the user's decisions, and the question. They cannot see the
   conversation, so the description must stand on its own.
4. **Ask.** Show the options neutrally, then the recommendation and how it was
   reached. Show any dissent left standing. Ask in one AskUserQuestion call,
   one question per design question, with the recommended option marked. A
   `USER'S CALL` gets no marker. Give the judge's lean in its description.

Do not write the decision anywhere. Report it, and leave recording it to the
user or to the workflow that asked the question.
