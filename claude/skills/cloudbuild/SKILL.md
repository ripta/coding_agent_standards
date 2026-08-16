---
name: cloudbuild
description: |
  Author, audit, or fix a Google Cloud Build `cloudbuild.yaml`, and create the
  matching GCB triggers. Use when a repo needs CI on Cloud Build, when an
  existing cloudbuild.yaml has drifted from standard, or when a repo has a
  config but no triggers.
model: sonnet
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, AskUserQuestion
---

You author and audit Google Cloud Build configs. A good config is short,
delegates its real work to a `Makefile` or `Dockerfile`, and drives every ref
type from one file.

Templates live in `templates/` next to this file. Read the one you need instead
of retyping it from memory.

| File | Use it for |
| --- | --- |
| `templates/ci-make.yaml` | The default. A test/lint gate driven through `make`, covering PR, default branch, and tags. |
| `templates/image-build.yaml` | Building and pushing a container image. |
| `templates/fragments.yaml` | Optional blocks: dependency cache, release-on-tag, multi-arch, tag retag. |
| `templates/triggers.md` | Trigger naming convention and the commands to create them. |

## Preference file

`~/.config/coding_agent_standards/cloudbuild.json` holds machine-local GCP
state. Never write these values into this skill. Never commit the file.

```json
{
  "project": "my-project",
  "region": "us-central1",
  "connections": {"my-gh-org": "my-gh-org"},
  "release": {"app_id": "0000000", "secret_name": "my-app-key"}
}
```

- `connections` maps a GitHub owner to its Developer Connect connection name.
- `release` is only needed when the config cuts GitHub releases on tags.

Precedence for each value: explicit in the user's request, then the preference
file, then detect it (see below) and offer to save. Validate before trusting a
cached value. A stale project or region should be re-asked, not worked around.

Detection fallbacks, in order:

- `project`: `gcloud config get-value project`.
- `region`: the region where the user's existing triggers already live. There is
  no all-regions listing, so probe candidate regions with
  `gcloud builds triggers list --region=<candidate> --format='value(name)'`
  until one returns results. Ask the user rather than probing indefinitely.
- `connections`: `gcloud developer-connect connections list --location=<region>`.

## Step 1: Detect, without asking

Do all of this before any question. Most answers are already on disk.

1. `git remote get-url origin` gives the GitHub owner and repo.
2. `git symbolic-ref refs/remotes/origin/HEAD` gives the default branch. Fall
   back to `git branch --show-current`.
3. Glob for `cloudbuild*.yaml`. If one exists, this is an audit, not an author.
4. Read the `Makefile` and list its targets. Note whether `ci`, `test`, `lint`,
   `build`, and `dist` exist.
5. Glob for `Dockerfile*`.
6. Identify the toolchain from the lockfile or manifest: `go.mod`, `Cargo.toml`,
   `package.json`, `build.zig`, `pyproject.toml`.
7. Check for prior builds, which set the timeout in step 4:

   ```sh
   gcloud builds list --region=<region> --limit=40 \
     --filter='substitutions.TRIGGER_NAME ~ ^<repo>- AND status=SUCCESS' \
     --format='csv[no-heading](substitutions.TRIGGER_NAME,startTime,finishTime)'
   ```

8. Check for existing triggers:
   `gcloud builds triggers list --region=<region> --format='value(name)'`.

Report what you found in a few lines before asking anything.

## Step 2: Ask once, up front

Make a single `AskUserQuestion` call. Every question the task needs goes in that
one call, before you write a single line. Do not ask, write, then ask again.

Skip any question already settled by the request or by step 1. If detection
answered everything, write nothing yet and confirm the plan in one line instead.

Ask only from this set:

- **Scope.** Test and lint gate only? Gate plus build and push an image? Or gate
  plus image plus a GitHub release on tags?
- **Refs.** PR and default branch? Or PR, default branch, and tags?
- **Entrypoint.** Only when the Makefile has several plausible targets and no
  `ci` target. Offer the detected targets as options.
- **Triggers.** Create them now, or emit the commands only?

## Step 3: Write the config

Start from the template that matches the scope. Adapt it. Do not paste blocks
the repo does not need.

`ci-make.yaml` and `image-build.yaml` each carry a `cut here` line. Everything
above it is a note to you and never reaches the repo. Everything below it is
sized the way a shipped config should be sized. Treat that length as the
target, not as a floor to build on.

**Route work through an entrypoint.** A step should call `make <target>` or
`docker build`. If the repo has neither a Makefile nor a Dockerfile, inline the
commands, and add a header comment saying they belong in a Makefile. Do not
create a Makefile as a side effect of this skill.

**One file, all refs.** A single `cloudbuild.yaml` drives PR, default branch,
and tag builds. Each step guards on `$TAG_NAME` or `$BRANCH_NAME`, so a branch
build pays only for the gate and a tag build pays only for the release path.
Split into a second file only when a pipeline is genuinely separate and
non-gating. `cloudbuild.bench.yaml` is the example.

A guard needs something to skip past. When every step is the gate, and the repo
has no tag trigger, write no guard. Dead guards mislead, and a `$TAG_NAME` guard
silently disables the gate the day someone adds a tag trigger. This is the
normal shape for a gate-only repo, so it needs no comment defending itself.

**Debian base images.** Prefer `debian:trixie`, `debian:bookworm`,
`golang:1.X-trixie`, or `rust:1-trixie`. Pin an older Debian only for a reason,
and write that reason in the header. Avoid Alpine.

**Write a short header comment.** Four to six lines, and shorter than the YAML
it heads. It names the triggers that drive the file. It records the choices a
reader would question. Nothing else.

A comment earns its place only when the YAML cannot say the thing itself.
Before keeping a line, look at what is already visible two lines below it.

Do not write:

- A "what it does" summary. The steps are right there.
- Prose restating a step's commands.
- A note about config that is absent. An unset `options.pool` needs no comment.
- Section headers like `What it does:` or `Non-obvious choices:`. A six-line
  comment does not need structure.
- A defense of the timeout rung. The number is not surprising.
- An `echo` of the branch or commit. Cloud Build already displays both.

Do write, one short sentence each:

- The triggers, by name and region.
- Why a step sits where it does, when the order is load-bearing.
- Why a version or image is pinned against the obvious choice.
- Why a guard the reader expects is absent.

Overexplaining is a defect, not thoroughness. It buries the two lines that
matter under twenty that do not.

### Substitution escaping

This is where these files break. Get it right.

- `$TAG_NAME`, `$BRANCH_NAME`, `$SHORT_SHA`, `$COMMIT_SHA`, `$PROJECT_ID`, and
  `$BUILD_ID` are Cloud Build substitutions. Single `$`. They resolve before the
  step runs.
- A shell variable set inside the step needs `$$VAR`. A single `$` there makes
  Cloud Build try to substitute it and fail.
- `${_CUSTOM}` is a user-defined substitution declared under `substitutions:`.
- Unset built-ins expand to the empty string. That is exactly why
  `if [[ -n "$TAG_NAME" ]]` works as the build-type guard.
- Set `options.dynamicSubstitutions: true` when a substitution references
  another one, such as `_CACHE_BUCKET: 'gs://${PROJECT_ID}_cloudbuild/x'`.

## Step 4: Set the timeout

Always set `timeout`. Never omit it.

Compute it from measured data when step 1 found prior builds. `gcloud builds
list` leaves the `duration` column empty, so subtract `startTime` from
`finishTime` yourself. Take the longest successful build. Multiply it by three.
Round up to the next rung, and clamp the result to `600s`-`2700s`.

| Rung | Shape |
| --- | --- |
| `600s` | One test or build step. A plain `docker build`. |
| `900s` | Several steps, or an image build plus push. |
| `1800s` | Heavy compile, a compiler matrix, or a cross-compile. |
| `2700s` | Ceiling. |

With no build history, pick the rung from the shape.

Never exceed `2700s`. A higher value needs an explicit request from the user
plus a comment recording why. Higher timeouts have backfired before. They let a
hung build sit there burning quota instead of failing it.

## Step 5: Triggers

Read `templates/triggers.md`. It holds the naming convention, the trigger YAML,
and the exact commands.

Emit the commands and show what they would create. Then ask before running them.
Nothing reaches GCP without confirmation.

After creating a trigger, verify it with
`gcloud builds triggers describe <name> --region=<region>`.

## Audit mode

When the repo already has a `cloudbuild*.yaml`, report before you edit. List
findings worst first, then ask which to apply. Never edit as you go.

Check, in this order of severity:

1. `options.pool` is set. This opts into a private pool. Always a violation.
   The smallest private pool is already around 20x the default pool's capacity,
   and it is billed for that capacity.
2. `timeout` is absent, or above `2700s` with no comment justifying it.
3. `options.machineType` is set. The default pool is covered by free-tier quota.
4. `$` used where `$$` is needed, or the reverse.
5. A base image outside the Debian family, with no reason given.
6. Inline command blocks that duplicate targets the Makefile already has.
7. Separate config files per ref type that could be one guarded file.
8. `docker buildx create --name X` paired with a `|| docker buildx use Y` where
   `Y` is a different name. The fallback silently targets the wrong builder.
9. A hardcoded project ID where `$PROJECT_ID` belongs.
10. No header comment naming the triggers.
11. A comment block longer than the YAML it heads. Check for the tells: a
    "what it does" summary, prose restating the steps, notes about absent
    config, a defense of the timeout. Template scaffolding shipped verbatim is
    the usual cause. Cut to the triggers plus the surprises.

Audit covers the config file. Trigger drift is out of scope.

## Dependency caching

Do not add a cache to a new config. Propose it only after builds have run and
the numbers justify it.

The bar: builds are slow, and the slow part is fetching or compiling
dependencies rather than the project's own code. Quote the measured duration and
estimate the saving before suggesting it. A three-minute build does not need a
cache.

When it does clear the bar, use the restore and save pair in
`templates/fragments.yaml`. It keys on a hash of the lockfile and toolchain pin,
restores on every build, and writes only from the default branch.

## Hard rules

- Never set `options.pool`. No exceptions.
- Never set `options.machineType`.
- Always set `timeout`, never above `2700s`.
- Prefer Debian base images.
- Steps call `make` targets or `docker build`, not long inline scripts.
- The header comment stays under six lines, and shorter than the YAML below it.
- Ship no comment the YAML already makes obvious.
- One config drives every ref type, guarded on `$TAG_NAME` and `$BRANCH_NAME`.
- Never write GCP project, region, or secret names into this skill.

## Verified gcloud behavior

These cost round trips if you assume otherwise:

- `gcloud builds list` and `gcloud builds triggers list` default to the `global`
  region. Regional triggers do not appear. Always pass `--region`.
- `--region=-` is rejected. There is no all-regions listing.
- There is no `gcloud builds triggers export`. Use `describe --format=yaml`.
- `gcloud developer-connect` takes `--location`, not `--region`.
- The `duration` output field on `gcloud builds list` comes back empty. Compute
  from `startTime` and `finishTime`.
- `gcloud` reads `~/.config/gcloud`. If that path is sandbox-denied, gcloud
  fails with a Python traceback about `active_config` rather than a clean error.
