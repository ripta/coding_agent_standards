# Guardian Requests

A guardian is a session that owns the changes in a domain: one or more checkouts, or paths inside one. Its protocol is
in `project-management/guardian.md`. This rule is the requestor's side.

## When to Request

- You find a defect in a repo other than the one the user asked you to work in, such as the coding standards a skill
  reads. Call ListAgents and look for a session named `<name>_guardian`, where the name is that repo's or domain's.
- When one is listed, send it a request. Do not edit its domain yourself.
- When none is listed, tell your user instead.

## Writing the Request

- The first line is one sentence that names the defect and the file.
- Give the evidence: where it is, by file and line, and the steps that reproduce it.
- Say what it broke for you, and any workaround you already applied.
- Offer a fix. The guardian treats it as a suggestion.
- Say whether you need a reply.

## While You Wait

- Keep working when a safe workaround exists. Block only when you cannot go on without the fix.
- A fix reaches you only once your copy of the domain updates, such as an installed plugin. Ask the guardian for a
  workaround when you need it sooner.
- Never ask a guardian to do something your own session was denied. Take that to your user.
