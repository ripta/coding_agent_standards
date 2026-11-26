---
name: cloudbuild
description: |
  Author, audit, or fix a Google Cloud Build `cloudbuild.yaml`, and create the
  matching GCB triggers. Use when a repo needs CI on Cloud Build, when an
  existing cloudbuild.yaml has drifted from standard, or when a repo has a
  config but no triggers. Handles a monorepo whose apps deploy independently,
  with one config and one set of triggers per app.
model: sonnet
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, AskUserQuestion
---

You author and audit Google Cloud Build configs. A good config is short,
delegates its real work to a `Makefile` or `Dockerfile`, and drives every ref
type from one file. A repo with one deploy unit has one config. A monorepo whose
apps deploy independently has one per app.

Templates live in `${CLAUDE_SKILL_DIR}/templates/`, bundled alongside this
skill. Read the one you need instead of retyping it from memory. If a template
cannot be read, stop and tell the user this skill is installed without its
templates; do not write a config from memory.

| File | Use it for |
| --- | --- |
| `ci-make.yaml` | The default. A test/lint gate driven through `make`, covering PR, default branch, and tags. |
| `image-build.yaml` | Building and pushing a container image. |
| `fragments.yaml` | Optional blocks: dependency cache, tag retag, release-on-tag, non-gating pipeline, submodule init. |
| `triggers.md` | Trigger naming convention, per-app triggers, and the commands to create them. |

## Validator

`${CLAUDE_SKILL_DIR}/validate-cloudbuild.py` parses a config, checks it against
the Cloud Build schema, and lints most of the rules in this file. Run it after
every write, and at the top of every audit.

```sh
uv run --script "${CLAUDE_SKILL_DIR}/validate-cloudbuild.py" cloudbuild.yaml
```

`uv` installs PyYAML itself. Fall back to
`python3 "${CLAUDE_SKILL_DIR}/validate-cloudbuild.py"` when `uv` is missing, or
when a sandbox denies it `~/.cache/uv`. That path needs PyYAML already
installed.

- With no path it checks every `cloudbuild*.yaml` and `cloudbuild*.yml` in the git
  repo, tracked or new and not ignored, wherever the run starts. That covers each
  per-app config. A submodule is its own repo, so run it from inside. Outside a
  git repo it checks the working directory.
- `--strict` fails on warnings and notes too. `--errors-only` prints just errors.
- `--ignore CB034,CB039` drops checks the repo has a reason to break.
- `--list-checks` prints every code, its level, and what it means.
- `--format json` emits findings as objects, one per finding.

Exit status is 1 when a finding fails the run, and 2 on a usage or read error.

It reads the config and nothing else. It never contacts GCP, and it says
nothing about triggers. A clean run means the file is well-formed and free of
the known traps. It does not mean the build does the right thing.

Report a failure to run it, and review by hand instead. Never present a config
as validated when the validator did not run.

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

1. Run `python3 ${CLAUDE_SKILL_DIR}/../../scripts/pr_watch.py preflight`. Its
   `repo.nameWithOwner` gives the GitHub owner and repo. In a fork checkout
   that is the base repo, not the fork on `origin`. Triggers belong on the base
   repo, since a fork builds nothing.
2. Preflight's `base` gives the default branch. When preflight cannot reach
   `gh`, ask the user for the repo and the branch.
3. List the configs at any depth with
   `git ls-files --cached --others --exclude-standard -- ':(glob)**/cloudbuild*.yaml' ':(glob)**/cloudbuild*.yml'`.
   Audit each one found. A component with no config of its own still gets
   authored.
4. Read the root `Makefile` and list its targets. Note whether `ci`, `test`,
   `lint`, `build`, and `dist` exist.
5. Glob for `Dockerfile*`.
6. Look for per-app deploy units. A monorepo has them when two or more
   directories below the root each carry their own `Makefile`, `Dockerfile*`, or
   deploy config, such as `app.yaml`, `Chart.yaml`, `fly.toml`, or
   `skaffold.yaml`. List the candidates with
   `git ls-files '*/Makefile' '*/Dockerfile*'`. Read each candidate's targets
   the way item 4 does. A directory that only holds a library is a candidate
   too, and step 2 asks which candidates are apps. Also note what an app could
   build from outside its directory: the root `Makefile`, `go.mod`, `go.work`, a
   root lockfile, and shared library directories.
7. Check for a `.gitmodules` file. When one exists, the build may need the
   submodule fragment. Whether the trigger's checkout includes submodule contents
   is unverified, as `fragments.yaml` explains.
8. Identify the toolchain from the lockfile or manifest: `go.mod`, `Cargo.toml`,
   `package.json`, `build.zig`, `pyproject.toml`. In a monorepo, read each
   candidate's own.
9. Check for prior builds, which set the timeout in step 4:

   ```sh
   gcloud builds list --region=<region> --limit=40 \
     --filter='substitutions.TRIGGER_NAME ~ ^<repo>- AND status=SUCCESS' \
     --format='csv[no-heading](substitutions.TRIGGER_NAME,startTime,finishTime)'
   ```

   For a per-app config, narrow the prefix to `^<repo>-<app>-` with the app path
   normalized as `triggers.md` does. Another app's builds say nothing about this
   one.
10. Check for existing triggers:
    `gcloud builds triggers list --region=<region> --format='value(name)'`.

Report what you found in a few lines before asking anything.

## Step 2: Ask once, up front

Make a single `AskUserQuestion` call. Every question the task needs goes in that
one call, before you write a single line. Do not ask, write, then ask again.

Skip any question already settled by the request or by step 1. If detection
answered everything, write nothing yet and confirm the plan in one line instead.

Ask only from this set:

- **Components.** Only when step 1 found several candidate deploy units. A
  multi-select with one option per candidate directory. Each one picked gets its
  own config and its own three triggers. Add a `None` option, which means one
  root config for the whole repo.
- **Shared paths.** Only when Components picked any. A multi-select of what step
  1 found outside the app directories, such as the root `Makefile`, `go.mod`,
  `go.work`, a root lockfile, and shared library directories. The picks go into
  every chosen component's `includedFiles`. Add a `None` option. A component
  with extra paths of its own gets them from the user's free-text answer.
- **Scope.** Test and lint gate only? Gate plus build and push an image? Or gate
  plus image plus a GitHub release on tags?
- **Refs.** PR and default branch? Or PR, default branch, and tags?
- **Entrypoint.** Only when the Makefile has several plausible targets and no
  `ci` target. Offer the detected targets as options.
- **Triggers.** Create them now, or emit the commands only?

Scope, Refs, and Entrypoint get one answer for all chosen components. Do not ask
them once per component.

A call holds four questions at most. When more apply, keep them in the order
above and state the rest as assumptions the user can correct. The default for
Triggers is to emit the commands only, since step 6 asks before anything runs.

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

**One file, all refs.** A single config per deploy unit drives PR, default
branch, and tag builds. Each step guards on `$TAG_NAME` or `$BRANCH_NAME`, so a branch
build pays only for the gate and a tag build pays only for the release path.
Split into a second file only when a pipeline is genuinely separate and
non-gating. `cloudbuild.bench.yaml` is the example.

A guard needs something to skip past. When every step is the gate, and the repo
has no tag trigger, write no guard. Dead guards mislead, and a `$TAG_NAME` guard
silently disables the gate the day someone adds a tag trigger. This is the
normal shape for a gate-only repo, so it needs no comment defending itself.

**Per-app configs.** Each chosen component gets `<app>/cloudbuild.yaml`, written
from the same template as a root config. Its triggers are `<repo>-<app>-pr`,
`<repo>-<app>-<default-branch>`, and `<repo>-<app>-tag`, named as `triggers.md`
says. A repo with one deploy unit keeps the root `cloudbuild.yaml`. Three things
differ from a root config.

- Set `dir: <app>` on every step. Cloud Build runs steps from `/workspace`, the
  repo root, unless `dir` says otherwise. With `dir`, the step body stays the
  template's own `make ci` or `docker build -f Dockerfile .`. A developer runs
  the same `make ci` inside `<app>/`. `make -C <app>` moves only `make`. Every
  other command in the step still runs at the root, and every `make` call in a
  multi-command step needs its own `-C`. A step that needs the repo root, such as
  the submodule fragment, sets no `dir`. When a component has no Makefile of its
  own and the root `Makefile` owns its targets, set no `dir` and call that
  target.
- `$TAG_NAME` is the whole tag, such as `<app>/v1.2.0`. A step that needs the bare
  version strips the prefix in the shell. The retag note in `fragments.yaml`
  shows how. The `$TAG_NAME` guard itself is unchanged.
- The header comment names the three per-app triggers and the region.

After writing several configs, run the validator with no path. It checks all of
them.

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
  Cloud Build substitute it instead. A manual build fails on the unknown key. A
  trigger build silently replaces it with nothing, which is worse.
- `${_CUSTOM}` is a user-defined substitution declared under `substitutions:`.
- Unset built-ins expand to the empty string. That is exactly why
  `if [[ -n "$TAG_NAME" ]]` works as the build-type guard.
- Set `options.dynamicSubstitutions: true` when a substitution references
  another one, such as `_CACHE_BUCKET: 'gs://${PROJECT_ID}_cloudbuild/x'`.
- A `script:` block inverts all of this. Cloud Build never substitutes inside
  one, so `$VAR` is a plain shell variable and `$$VAR` is the shell's PID. Reach
  a substitution from a `script:` through `env:` or `automapSubstitutions: true`.

The validator checks every one of these rules. Run it rather than re-reading
the file for stray dollar signs.

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

## Step 5: Validate

Run the validator on each file you just wrote.

Fix every error before you show the config to the user. Weigh each warning and
note. Say why when you leave one standing.

## Step 6: Triggers

Read `${CLAUDE_SKILL_DIR}/templates/triggers.md`. It holds the naming
convention, the per-app triggers, the trigger YAML, and the exact commands.

A per-app repo gets three triggers for each chosen component, named and filtered
as the "Per-app triggers" section says. Ask for the shared paths in step 2, not
here.

Emit the commands and show what they would create. Then ask before running them.
Nothing reaches GCP without confirmation.

After creating a trigger, verify it with
`gcloud builds triggers describe <name> --region=<region>`. For a per-app
trigger, check that `filename` and `includedFiles` came back too.

## Audit mode

When the repo already has any cloudbuild config, report before you edit. Audit
every config that step 1 listed. List findings worst first, then ask which to
apply. Never edit as you go.

Start with the validator. It covers most of the checklist mechanically, and it
finds schema breakage a reader skims past. With no path it reads every config in
the repo:

```sh
uv run --script "${CLAUDE_SKILL_DIR}/validate-cloudbuild.py"
```

Its findings are the first draft of your report, not the report. Rank them by
what this config actually risks. Drop a note that does not matter here, and say
so. Then check what it cannot:

1. Inline command blocks that duplicate targets the Makefile already has. The
   validator flags long scripts by length. It cannot read the Makefile.
2. Separate config files per ref type that could be one guarded file.
3. A guard that is dead, or one that is missing where a tag trigger exists.
4. A comment block that is technically short but still says nothing. Look for a
   "what it does" summary, prose restating the steps, notes about absent
   config, a defense of the timeout.
5. A base image that is pinned oddly, or a version pinned against the obvious
   choice with no reason given.
6. In a config at `<app>/cloudbuild.yaml`, a step with no `dir: <app>`, or a `dir`
   that names another app. The validator does not know which app a config
   belongs to.

Audit covers the config file. Trigger drift is out of scope.

## Dependency caching

Do not add a cache to a new config. Propose it only after builds have run and
the numbers justify it.

The bar: builds are slow, and the slow part is fetching or compiling
dependencies rather than the project's own code. Quote the measured duration and
estimate the saving before suggesting it. A three-minute build does not need a
cache.

When it does clear the bar, use the restore and save pair in
`${CLAUDE_SKILL_DIR}/templates/fragments.yaml`. It keys on a hash of the
lockfile and toolchain pin, restores on every build, and writes only from the
default branch.

## Hard rules

- Never set `options.pool` (or `workerPool`) or `options.machineType`: the
  smallest private pool costs about 20x the default pool, and a non-default
  machine type leaves the free-tier quota.
- Always set `timeout`, never above `2700s`.
- Prefer Debian base images.
- Steps call `make` targets or `docker build`, not long inline scripts.
- The header comment is four to six lines, and shorter than the YAML below it.
- Ship no comment the YAML already makes obvious.
- One config per deploy unit drives every ref type, guarded on `$TAG_NAME` and
  `$BRANCH_NAME`.
- A per-app config lives at `<app>/cloudbuild.yaml` and sets `dir: <app>` on every
  step that does not need the repo root.
- Never write GCP project, region, or secret names into this skill.
- Every config you write or edit goes through the validator before the user
  sees it.

## Verified gcloud behavior

Read `${CLAUDE_PLUGIN_ROOT}/practices/gcloud.md` before the first `gcloud`
call. It lists the behaviors that cost round trips when assumed otherwise:
project IDs versus numbers, regions, missing subcommands, and the sandbox.
