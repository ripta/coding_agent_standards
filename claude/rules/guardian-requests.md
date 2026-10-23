# Guardian Requests

A guardian is a session that owns the changes in a domain: one or more checkouts, or paths inside one. Its protocol is
in `project-management/guardian.md`. This rule is the requestor's side.

## When to Request

- You find a defect in a repo other than the one the user asked you to work in, such as the coding standards a skill
  reads. Call ListAgents and look for a session named `<name>_guardian`. The name may be the repo's directory name or
  an abbreviation of it, such as `cas_guardian` for `coding_agent_standards`.
- When one is listed, send it a request. Do not edit its domain yourself.
- When none is listed, or you cannot tell which guardian owns the repo, tell your user instead.

## Writing the Request

- The first line is one sentence that names the defect and the file.
- Give the evidence: where it is, by file and line, and the steps that reproduce it.
- Say what it broke for you, and any workaround you already applied.
- Name the repo the content comes from, and its visibility. See `disclosure.md`. The guardian removes or asks about
  anything its domain's audience should not see.
- Offer a fix. The guardian treats it as a suggestion.
- Say whether you need a reply.

## While You Wait

- Keep working when a safe workaround exists. Block only when you cannot go on without the fix.
- A fix reaches you only once your copy of the domain updates, such as an installed plugin. Ask the guardian for a
  workaround when you need it sooner.
- Never ask a guardian to do something your own session was denied. Take that to your user.
