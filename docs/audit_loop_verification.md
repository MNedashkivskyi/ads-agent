# Audit → Recovery loop — staging verification runbook

End-to-end checklist for the free-audit funnel and its retention loop:
**reveal → bridge → fix → recovered**. Use it after deploying any of the loop's
PRs (ads-agent #294/#295/#296, approve-ads-bot #144/#145/#146).

## What automated tests already cover

- **Unit** (`uv run pytest -m "not integration"`, runs in CI): the waste engine,
  vertical inference, the bridge use-case (fakes), the recovery reconciliation
  math, the finding→fix mapping, and that `ExecuteRecommendationUseCase` books a
  projected ledger entry on success.
- **Integration** (`-m integration`, **not** run in CI — needs Postgres): the
  bridge through real repositories + the recovery-ledger repo SQL. Run them against
  any Postgres:

  ```bash
  cd backend
  TEST_DATABASE_URL=postgresql+asyncpg://USER:PASS@HOST:5432/DBNAME \
    uv run pytest tests/integration/test_audit_bridge_integration.py \
                  tests/integration/test_recovery_ledger_integration.py -v
  ```

  Point `TEST_DATABASE_URL` at a throwaway DB (the fixture runs
  `Base.metadata.create_all`; never a production DB).

## What only a human can verify (live OAuth / GAQL / Google Ads mutations)

These paths are intentionally thin and were not exercisable in unit tests. Do them
once against staging with a real Google Ads account.

### 1. Audit scan (read-only OAuth + GAQL)
1. Open `/audit`, click connect, complete Google OAuth with the **read-only** scope.
2. The `/audit/scanning` page should poll, then redirect to `/audit/r/{reportId}`.
3. **Expect:** a red headline waste figure, a per-finding breakdown, and under each
   finding a *"Jak to naprawimy: …"* line (the fix mapping).
4. **DB check:** `audit_sessions` row `status='ready'`, `google_customer_id` set; a
   `waste_reports` row tied to it; `waste_findings` rows.

### 2. Bridge (sign up + write-enabled link)
1. From the reveal, click the CTA → sign up.
2. Link Google Ads with the **write** scope for the **same** customer id you audited.
3. Land on `/app`. **Expect:** the red "Twój audyt wykrył X zł" banner listing the
   audited findings, each with a **Napraw** button.
4. **DB check:** the `audit_sessions` row is now `status='promoted'` with `user_id`
   and `account_id` set; its `waste_reports.account_id` now points at the account.
   `GET /api/audit/accounts/{id}/report` and `/findings` return the data.
5. **Negative:** link a *different* customer id — the audit must NOT be claimed
   (banner absent; session stays un-promoted).

### 3. Fix (apply a recommendation)
1. Click **Napraw** on a finding → `/app/recommendations?kind=…` filtered to that fix.
2. Apply one actionable recommendation; wait for it to reach `EXECUTED`.
3. **DB check:** a `recovery_ledger` row appears — `method='projected'`,
   `realized_saving_micros` = the rec's `estimated_monthly_savings_micros`,
   `recommendation_id` set, `measured_at` NULL.

   ```sql
   select method, realized_saving_micros, measured_at, baseline_metric
   from recovery_ledger where account_id = '<ACCOUNT_UUID>' order by applied_at desc;
   ```

### 4. Recover (the meter)
- On `/app`, the green **"Odzyskaliśmy X zł z Y zł marnowanych rocznie"** meter shows,
  with the applied-fixes count. `GET /api/audit/accounts/{id}/recovery` returns
  `recovered_micros`, `applied_count`, `identified_annual_waste_micros`.

### 5. Settle (projected → measured)
- The `settle_recovery_ledger_task` runs daily at 06:30 UTC and reconciles entries
  older than 28 days. To verify sooner, invoke it manually on the worker:

  ```python
  from adcopilot.interfaces.worker.audit_tasks import settle_recovery_ledger_task
  settle_recovery_ledger_task.apply()  # or .delay() on the worker
  ```

- **Expect:** entries past the window flip to `method='measured'` with `measured_at`
  set; `realized_saving_micros` recomputed from pre/post-apply campaign spend
  (`reconcile_realized_saving`). Entries inside the window are untouched.

## Thin spots to watch in logs
- `GoogleAdsAuditScanReader` (live GAQL pull) — confirm the windowed query returns
  campaigns/keywords/search-terms and that vertical inference picks a sane vertical.
- The settle task's per-campaign spend read (`get_campaigns_date_range`) — confirm a
  paused/negated entity's post-window spend really drops, so `realized ≈ projected`.
