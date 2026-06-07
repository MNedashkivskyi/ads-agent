# CI & deploy gating (LAUNCH-022)

## CI (`.github/workflows/ci.yml`)
Runs on every PR and push to `master`:
- **ruff check** + **ruff format --check** — blocking.
- **mypy** — re-enabled, currently **non-blocking** (`continue-on-error: true`).
  There is a backlog of ~470 pre-existing type errors. The step runs so type
  problems are visible; burn the backlog down (or scope mypy to cleaned
  packages) and then flip `continue-on-error` to `false` to make it a hard gate.
- **pytest** (non-integration) — blocking.
- **pip-audit** — blocking on HIGH/CRITICAL CVEs.

## Branch protection (manual — repo admin setting)
CI does not gate Railway deploys by itself. To ensure only green commits ship:
1. GitHub → Settings → Branches → add a rule for `master`.
2. Require status checks to pass before merging; select the `lint` and `test`
   jobs.
3. Require branches to be up to date before merging.
4. In Railway, deploy the API/worker/beat services from `master` only, so
   deploys track gated commits.

## Mypy ratchet plan
1. Keep `continue-on-error: true` until the count trends to zero.
2. Optionally add per-package `mypy` runs (e.g. `domain/`, `application/`) as
   hard gates while the rest stays non-blocking.
3. Flip to blocking once clean.
