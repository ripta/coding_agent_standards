# GitHub Issues

Group kinds and their `id` forms:

- `tracking-issue`: `owner/repo#N`, a parent issue whose sub-issues are the tickets
- `milestone`: `owner/repo/<milestone title>`
- `label`: `owner/repo/<label name>`

The tracker entry's `assignee` is a GitHub login. `@me` also works with `gh`.
The optional `site` names a GitHub Enterprise host. Pass it as
`--hostname` to `gh api` and set `GH_HOST` for other `gh` commands.

## Interfaces

Prefer the `gh` CLI. Check `gh auth status` before the first call and stop
if it is not authenticated. A GitHub MCP server works too if one is connected.
Map the operations below onto its issue tools.

Pass bodies through files in the scratch directory (`--body-file`), never
inline, so quoting cannot corrupt them.

## Operations

- **List group:**
  - `tracking-issue`: `gh api repos/<owner>/<repo>/issues/<N>/sub_issues --paginate`.
    Sub-issues can live in other repositories. Take each item's
    `repository_url`, not the parent's repo. If the parent has no
    sub-issues but its body has a task list (`- [ ] #123`, `- [ ] owner/repo#123`),
    the task list is the membership.
  - `milestone`:

    ```sh
    gh issue list -R <owner>/<repo> --milestone "<title>" --state all \
      --limit 1000 \
      --json number,title,state,stateReason,assignees,body,updatedAt,url
    ```

  - `label`: the same call with `--label "<name>"`.

  `--limit 1000` is a cap, not pagination. If a listing returns exactly the
  cap, page with `gh api --paginate` instead.
- **Read ticket:** `gh issue view <N> -R <owner>/<repo> --json <fields>` with
  `title,body,state,stateReason,assignees,comments,url`.
- **Comment:** `gh issue comment <N> -R <owner>/<repo> --body-file <file>`.
- **Edit description:** write the full new body to a file, then
  `gh issue edit <N> -R <owner>/<repo> --body-file <file>`.
- **Close:** `gh issue close <N> -R <owner>/<repo> --reason completed`
  (`--reason "not planned"` for won't-do or duplicate). Put the closing
  comment in a separate `gh issue comment` call so it is never lost to a
  failed close. For a tracking issue that uses a task list, also tick the
  child's box in the parent body. That edit is part of the same approved
  action.
- **Assign:** `gh issue edit <N> -R <owner>/<repo> --add-assignee <assignee>`.
- **Create in group:**
  `gh issue create -R <owner>/<repo> --title ... --body-file <file>` plus
  `--milestone "<title>"` or `--label "<name>"`. For a tracking issue, attach
  the new issue as a sub-issue:

  ```sh
  id=$(gh api repos/<owner>/<repo>/issues/<N> --jq .id)
  gh api -X POST repos/<owner>/<repo>/issues/<parent>/sub_issues \
    -F sub_issue_id="$id"
  ```

  `sub_issue_id` takes the issue's numeric `id`, not its number.

## Ticket references

Commits cite issues as `#N` or `owner/repo#N`, often behind a closing keyword
(`Fixes #12`). A squash-merge subject's trailing `(#N)` is usually the pull
request, not an issue. Confirm that a number is in the group's listing
before treating it as a ticket.
