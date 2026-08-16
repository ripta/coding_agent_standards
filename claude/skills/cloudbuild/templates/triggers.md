# Triggers

Triggers are regional. Read `region`, `project`, and the connection name from
`~/.config/coding_agent_standards/cloudbuild.json`.

## Naming convention

Three triggers per repo. A repo without tagged releases needs only the first
two.

| Trigger | Fires on | Config file |
| --- | --- | --- |
| `<repo>-pr` | PR against the default branch | `cloudbuild.yaml` |
| `<repo>-<default-branch>` | push to the default branch | `cloudbuild.yaml` |
| `<repo>-tag` | push of a `v*` tag | `cloudbuild.yaml` |

Rules that are easy to get wrong:

- **Name** uses the *actual* default branch. A repo on `master` gets
  `<repo>-master`, not `<repo>-main`.
- **Description** is `<owner>/<repo> <role>`, where role is `PR`, the actual
  branch name, or `tag`. Note `PR` is uppercase and the others are lowercase.
- **`on:` tag** is role-based, not branch-based. The default-branch trigger is
  always tagged `on:main`, even when that branch is called `master`. One tag
  filter then selects every default-branch trigger across all repos.
- A repo name containing a dot is normalized in the trigger name and the owner
  tag, but not in the description and not in the repository link. `imple.me`
  becomes trigger `imple-me-pr`, tag `ripta/imple-me`, description
  `ripta/imple.me`, link `ripta-imple.me`.

An extra pipeline gets a purpose suffix and a `for:` tag. A benchmark job on
the default branch is `<repo>-bench`, described `<owner>/<repo> bench`, tagged
`<owner>/<repo>`, `on:main`, `for:bench`, reading `cloudbuild.bench.yaml`.

Manual triggers fall outside this scheme. They have no event, so they get no
`on:` tag. Tag them `<owner>/<repo>` plus `for:<purpose>`, matching how an extra
pipeline is tagged.

## Repository link

Two 2nd-gen event configs exist, and an established project may hold both. New
triggers use `developerConnectEventConfig`. Older ones use
`repositoryEventConfig`, which points at a Cloud Build `repositories` resource
rather than a Developer Connect link. Read an existing trigger before editing
it, and preserve whichever config it already has.

New triggers bind to a Developer Connect git repository link, not to a raw
GitHub repo:

```
projects/<project>/locations/<region>/connections/<owner>/gitRepositoryLinks/<owner>-<repo>
```

The connection is named after the GitHub owner. Confirm both before creating
anything:

```sh
gcloud developer-connect connections list --location=<region>

gcloud developer-connect connections git-repository-links list \
  --connection=<owner> --location=<region> \
  --format='value(name,cloneUri)'
```

If the repo has no link yet, create it before the trigger. A trigger pointing
at a missing link fails at create time.

## Creating the triggers

`gcloud builds triggers create` has no Developer Connect subcommand. Its
`github --repository=` flag takes a Cloud Build 2nd-gen `repositories` resource,
which is a different resource from a `gitRepositoryLinks` one. Use
`triggers import` instead, which accepts the full trigger body.

Write the YAML, show the user what it will create, and ask before running.

```yaml
# pr.yaml
name: REPO-pr
description: OWNER/REPO PR
filename: cloudbuild.yaml
tags:
  - OWNER/REPO
  - on:pr
developerConnectEventConfig:
  gitRepositoryLink: projects/PROJECT/locations/REGION/connections/OWNER/gitRepositoryLinks/OWNER-REPO
  gitRepositoryLinkType: GITHUB
  pullRequest:
    # The base branch, anchored.
    branch: ^main$
    commentControl: COMMENTS_ENABLED_FOR_EXTERNAL_CONTRIBUTORS_ONLY
```

```yaml
# main.yaml
name: REPO-main
description: OWNER/REPO main
filename: cloudbuild.yaml
tags:
  - OWNER/REPO
  - on:main
developerConnectEventConfig:
  gitRepositoryLink: projects/PROJECT/locations/REGION/connections/OWNER/gitRepositoryLinks/OWNER-REPO
  gitRepositoryLinkType: GITHUB
  push:
    branch: ^main$
```

```yaml
# tag.yaml
name: REPO-tag
description: OWNER/REPO tag
filename: cloudbuild.yaml
tags:
  - OWNER/REPO
  - on:tag
developerConnectEventConfig:
  gitRepositoryLink: projects/PROJECT/locations/REGION/connections/OWNER/gitRepositoryLinks/OWNER-REPO
  gitRepositoryLinkType: GITHUB
  push:
    tag: ^v.+$
```

Then:

```sh
gcloud builds triggers import --source=pr.yaml   --region=REGION
gcloud builds triggers import --source=main.yaml --region=REGION
gcloud builds triggers import --source=tag.yaml  --region=REGION
```

`import` creates a trigger when the name is new and updates it in place when
the name already exists. Check for an existing trigger of that name first, so
an intended create does not silently overwrite something.

## Editing an existing trigger

`gcloud builds triggers update` has no Developer Connect subcommand, so editing
goes through the same import path. Describe, strip the output-only fields, patch
what changed, import back:

```sh
gcloud builds triggers describe NAME --region=REGION --format=json > in.json
python3 - <<'EOF'
import json, yaml
t = json.load(open('in.json'))
for k in ('id', 'createTime', 'resourceName'):
    t.pop(k, None)          # the API rejects these on import
t['tags'] = ['OWNER/REPO', 'on:pr']
yaml.safe_dump(t, open('out.yaml', 'w'), sort_keys=True)
EOF
gcloud builds triggers import --source=out.yaml --region=REGION
```

This preserves an inline `build:` spec and either event config shape, because it
only touches the keys being changed.

A trigger's name is immutable. Renaming means importing under the new name, then
deleting the old trigger. Confirm the new one exists before deleting the old.

## Verify

Always confirm after creating:

```sh
gcloud builds triggers describe REPO-pr --region=REGION --format=yaml
```

Check that `developerConnectEventConfig` came back populated. If it is missing
or the trigger came back in a different shape, the import did not round-trip.
Report that rather than assuming it worked.

## Commands that do not work

- `gcloud builds triggers list` with no `--region` reads the `global` region
  and shows nothing for regional triggers.
- `--region=-` is rejected. There is no all-regions listing. Probe regions.
- `gcloud builds triggers export` does not exist. Use
  `describe --format=yaml` and strip the output-only fields: `id`,
  `createTime`, and `resourceName`.
- `gcloud developer-connect` takes `--location`. Passing `--region` errors out.
