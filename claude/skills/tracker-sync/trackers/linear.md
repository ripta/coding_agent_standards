# Linear

Group kind: `project`. The group `id` is the project's name, slug, or ID. The
tracker entry's `assignee` is a Linear user ID, or `me` where the interface
accepts it.

## Interfaces

Use a connected Linear MCP server, or a Linear CLI if one is installed and
authenticated. Tool and command names differ between servers and CLIs.
Discover them first (search the available tools for "linear" and "issue"),
and map each operation below onto what exists. If neither an MCP server nor
a CLI is available, stop and ask. Never call the GraphQL API with a
hand-supplied token.

## Operations

- **List group:** the issues in the project, all states, with identifier,
  title, state (name and type), assignee, team, description, and URL. Save the
  result to the scratch directory. Page until the interface reports no more
  results.
- **Read ticket:** by identifier (`ENG-123`), with comments only when the
  verdict depends on them.
- **Comment:** markdown body.
- **Edit description:** read the current description, apply the change, and
  write the whole description back. Descriptions are markdown.
- **Close:** set the issue's state to one of its team's workflow states whose
  type is `completed`. Teams rename states, so match on type, not the name
  `Done`. Use a state of type `canceled` for won't-do or duplicate, and only
  when the approved action says so. When a team has several `completed` states,
  pick the one its other closed issues in the project use.
- **Assign:** set the issue's assignee to the tracker's `assignee`.
- **Create in group:** create the issue in the project. Linear requires a
  team. Use the team most of the project's issues belong to, and ask when
  the project spans teams evenly.

## Ticket references

Linear identifiers look like Jira keys (`ENG-123`), and so do proposal
identifiers. A key only counts as a ticket reference when it appears in the
group's listing.
