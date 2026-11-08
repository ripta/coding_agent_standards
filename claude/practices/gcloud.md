# gcloud

These are verified `gcloud` behaviors. Each one costs a round trip when you assume otherwise. Skills that call
`gcloud` cite this file instead of keeping their own copies.

## Projects

- `--project` takes a project ID, such as `my-proj`, not a project number, such as `134954827775`. `gcloud builds`
  rejects a number, and other command groups vary. An ID works everywhere.
- A Cloud Build details URL carries the project number, as `?project=<number>`. GitHub check runs link to these URLs.
  Resolve the number before passing it anywhere:

  ```sh
  gcloud projects describe <number> --format='value(projectId)'
  ```

- The plugin's `block-gcloud-project-number.sh` hook denies an all-digit `--project`, `gcloud config set project`, or
  `CLOUDSDK_CORE_PROJECT`. A project ID must start with a letter, so an all-digit value is always a number.

## Regions

- `gcloud builds list` and `gcloud builds triggers list` default to the `global` region. Regional builds and triggers
  do not appear. Always pass `--region`.
- `--region=-` is rejected. There is no all-regions listing. Probe each candidate region.
- `gcloud developer-connect` takes `--location`, not `--region`.

## Cloud Build

- There is no `gcloud builds triggers export`. Use `gcloud builds triggers describe <name> --format=yaml`.
- The `duration` output field on `gcloud builds list` comes back empty. Compute it from `startTime` and `finishTime`.

## Sandbox

- `gcloud` reads `~/.config/gcloud`. When the sandbox denies that path, gcloud fails with a Python traceback about
  `active_config` instead of a clean error. Run it through `cg_run`, or outside the sandbox.
- A missing login shows as an auth error. The user runs `! gcloud auth login`.
