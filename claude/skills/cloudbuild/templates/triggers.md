# Triggers

Triggers are regional. Read `region`, `project`, and the connection name from
`~/.config/coding_agent_standards/cloudbuild.json`.

## Naming convention

Three triggers per repo. A repo without tagged releases needs only the first
two. A monorepo whose apps deploy independently gets three per app. See
"Per-app triggers".

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

## Per-app triggers

Use these when the apps in a monorepo deploy independently. Each app has its own
config at `<app>/cloudbuild.yaml`, and each gets its own three triggers. A repo
with one deploy unit keeps the root `cloudbuild.yaml` and the three triggers
above.

`<app>` is the app's path from the repo root, such as `apps/api`.

| Trigger | Fires on | Config file |
| --- | --- | --- |
| `<repo>-<app>-pr` | PR against the default branch | `<app>/cloudbuild.yaml` |
| `<repo>-<app>-<default-branch>` | push to the default branch | `<app>/cloudbuild.yaml` |
| `<repo>-<app>-tag` | push of a `<app>/v*` tag | `<app>/cloudbuild.yaml` |

The rules above hold, with these changes.

- **Name** joins the repo, the app path, and the role with dashes. The role is
  the actual default branch for the middle trigger. Slashes and dots become
  dashes in every part, the way a dot in the repo name already does. Repo
  `imple.me`, app `apps/web`, branch `main` gives `imple-me-apps-web-main`. Two
  apps can normalize to one name, so check the names are distinct before writing
  anything.
- **Name length.** The API takes 1-64 characters, only alphanumerics and dashes,
  beginning and ending with an alphanumeric. Source: the `name` field of
  `BuildTrigger` in the Cloud Build REST reference,
  `https://docs.cloud.google.com/build/docs/api/reference/rest/v1/projects.triggers`.
  `gcloud builds triggers create github --help` states no limit. Count the
  longest of the three names before writing. When it passes 64, ask the user for
  a shorter label and use it in all three names. The label replaces the path in
  the name only.
- **Description** is `<owner>/<repo> <app> <role>`. The app path is written as it
  is, with slashes and dots intact, the way the description keeps the repo's dot.
  Example: `ripta/imple.me apps/web PR`.
- **Tags** are `<owner>/<repo>`, `on:<role>`, and `app:<app>`. The first two are
  unchanged, so `on:main` still selects every default-branch trigger across all
  repos. `app:<app>` is new. It takes the app path with dots turned into dashes,
  the way the owner tag does, and keeps the slashes. It is a `key:value` tag like
  the other two. `for:<purpose>` is the wrong key. It marks an extra pipeline, and
  an app named `bench` would collide with `for:bench`. A benchmark pipeline for an
  app combines them: `<repo>-<app>-bench`, tagged `<owner>/<repo>`, `on:main`,
  `app:<app>`, `for:bench`.
- **Config file** is `<app>/cloudbuild.yaml`, and an extra pipeline reads
  `<app>/cloudbuild.<purpose>.yaml`.
- **Tag filter** is `^<app>/v.+$`, which matches the release skill's per-app tags
  such as `apps/api/v1.2.0`. Escape regex characters in the path. `apps/web.v2`
  becomes `^apps/web\.v2/v.+$`.
- **`includedFiles`** is `<app>/**` plus the shared paths the app builds from.
  Ask the user for those. Offer what detection found, such as the root
  `Makefile`, `go.mod`, `go.work`, a root lockfile, or a shared library
  directory. A shared path left out of `includedFiles` means a change there
  skips this app's build.

Two behaviors of `includedFiles` are unverified. The Console documentation,
`https://docs.cloud.google.com/build/docs/automating-builds/create-manage-triggers`,
says the filter can be set only for events that push a branch or a new tag. It
says nothing about a PR trigger, and nothing about how a tag push compares
changed files. A tag that points at an already-pushed commit may match no
included file, so the tag trigger would never fire. The tag filter already
selects the app, so dropping `includedFiles` from the tag trigger is the fix if
that happens.

After creating the triggers, ask the user to push a test tag and to open a PR
that touches only the app. Confirm each starts a build.

```yaml
# api-pr.yaml
name: REPO-apps-api-pr
description: OWNER/REPO apps/api PR
filename: apps/api/cloudbuild.yaml
includedFiles:
  - apps/api/**
  - libs/shared/**
tags:
  - OWNER/REPO
  - on:pr
  - app:apps/api
developerConnectEventConfig:
  gitRepositoryLink: projects/PROJECT/locations/REGION/connections/OWNER/gitRepositoryLinks/OWNER-REPO
  gitRepositoryLinkType: GITHUB
  pullRequest:
    branch: ^main$
    commentControl: COMMENTS_ENABLED_FOR_EXTERNAL_CONTRIBUTORS_ONLY
```

The default-branch trigger is `main.yaml` below with the same changes. The tag
trigger differs only in its filter:

```yaml
# api-tag.yaml
name: REPO-apps-api-tag
description: OWNER/REPO apps/api tag
filename: apps/api/cloudbuild.yaml
includedFiles:
  - apps/api/**
  - libs/shared/**
tags:
  - OWNER/REPO
  - on:tag
  - app:apps/api
developerConnectEventConfig:
  gitRepositoryLink: projects/PROJECT/locations/REGION/connections/OWNER/gitRepositoryLinks/OWNER-REPO
  gitRepositoryLinkType: GITHUB
  push:
    tag: ^apps/api/v.+$
```

Import each file the way "Creating the triggers" shows, then describe each one
and check that `filename` and `includedFiles` came back.

## Repository link

Two 2nd-gen event configs exist, and an established project may hold both. New
triggers use `developerConnectEventConfig`. Older ones use
`repositoryEventConfig`, which points at a Cloud Build `repositories` resource
rather than a Developer Connect link. Read an existing trigger before editing
it, and preserve whichever config it already has.

New triggers bind to a Developer Connect git repository link, not to a raw
GitHub repo:

```text
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
