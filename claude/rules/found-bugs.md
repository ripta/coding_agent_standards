# Found Bugs

A session often finds a bug while doing something else: writing docs, reviewing a design, or implementing a milestone.
This rule applies to every kind of session. A bug found along the way never ends up only in chat. A list in the final
message is gone when the session ends.

A bug here includes a suspected one. Code that disagrees with its docs, its help text, a contract, or itself counts.

## Validate It

- Check every bug against the code before acting on it. Reproduce it when that is cheap: run the command, or write the
  failing test. Otherwise trace the code path that produces it.
- When the check shows the code is right, there is no bug, and nothing to file.
- When the check neither confirms nor refutes the bug, file it anyway, marked as not confirmed. See "Bugs" in
  `project-management/tracking.md`.

## Fix It or File It

Fix the bug in this session when both of these hold:

- The fix needs no design call. Choosing between two plausible behaviors is a design call. See `decision-making.md`.
- The bug blocks the current work, or sits next to it. Next to it means the same files, the same feature, or code the
  current work documents or depends on.

File every other bug. A bug that needs a design call gets a bug file that lays out the options. When it also blocks the
current work, ask the user about the design call.

A fix follows the usual rules:

- Write the regression test first, and see it fail. See "Before Implementing" in `work-discipline.md`.
- Land the fix as its own commit on the same branch. Fold it into the work's commit only when the two cannot be
  separated. Commit only where `git-workflow.md` allows. Where it does not, keep the fix in separate files or hunks, and
  name them in your report.
- A fixed bug gets no bug file. The fix commit's body says what the bug was and how it showed.
- A partial fix gets a bug file for the part that stays open. The file says what the fix already covers.

## File It

- The format and location are in "Bugs" in `project-management/tracking.md`. Read that section before filing the first
  bug of a session. A project's own bug process overrides it.
- Filing in an external issue tracker publishes the report. Draft it, and ask the user before filing.
- A bug in another repo goes to that repo's guardian. See `guardian-requests.md`.
- Commit bug files in their own commit, where `git-workflow.md` allows committing. Use the specs repo when the bugs
  directory lives there.
- A subagent that cannot commit, or may not edit outside its brief, reports the bug to its coordinator instead. The
  coordinator fixes it or files it.

## Report It

The session's final report names every bug it found. Each one says whether it was fixed, with the commit subject. Or it
says it was filed, with the bug file. Or it says it went to a guardian.
