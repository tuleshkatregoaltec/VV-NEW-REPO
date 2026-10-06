# Long-Running Jobs

Use this runbook for overnight raw scrapes and asset hydration backfills.

## Before Starting

- Run a small smoke with the same code path.
- Confirm the job is raw-only if bronze is not ready.
- Check that credentials and R2 settings are loaded.
- Check that the source has bounded work or a checkpoint.
- Confirm logs include progress counts and errors.
- Prefer chunked jobs over one large local-only run.

## Launch

Use Dagster jobs/assets when possible. For host-side raw R2 tests, make sure
`DAGSTER_HOME` points at a local host directory if the repo-level `dagster.yaml`
expects Docker-only Postgres.

Keep a log file when launching detached host runs:

```bash
mkdir -p var/logs var/dagster_host
export DAGSTER_HOME="$PWD/var/dagster_host"
```

Do not run competing browser-heavy scrapes unless the machine has enough memory
and CPU.

## Monitor

Check:

- Process is alive.
- Latest progress marker.
- Completed/total and errors.
- Rate and ETA from recent markers.
- Scratch file sizes if the source writes locally before upload.
- R2 object growth only for jobs that upload during the run.

For jobs that upload only at the end, no R2 growth is expected until completion.

## If A Job Looks Stalled

- Check whether the progress interval is simply too sparse.
- Check child browser/process CPU.
- Look for timeout/error logs.
- Reproduce one or two items with endpoint-level timing.
- Add per-request timeouts before restarting an overnight run.

Do not kill a run just because R2 is not growing unless the source is supposed to
stream/upload per item.

## After Completion

- Confirm `RUN_SUCCESS` or Dagster materialization success.
- Record the manifest key.
- Check row counts in the manifest.
- For asset jobs, inspect inventory status counts.
- Note any source limitations or endpoint findings in the source README.
