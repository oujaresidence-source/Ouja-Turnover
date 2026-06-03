# Expenses Export Repair Plan

## Stage 1 Audit Findings

- The dashboard uses legacy expense statuses (`captured`, `ready`, `held`, `in_transit`, `posted`, `failed`, `discarded`) directly in filters, cards, sync state, and summary counts. This makes "sent", "verified", "stuck", and "needs review" overlap.
- `POST /api/expenses/post` does the Hostaway write and immediate verification inside the same request. If Hostaway accepts the write but the read-back is delayed, unreachable, cached, or dry-run, the expense can remain in an unclear pending state with no durable background job.
- "Posted" currently means two different things in old data: optimistic sent and verified. The code tries to protect truth by only counting `posted + hostaway_verified`, but the UI still labels several transitions as posted.
- The bulk "post all ready" action loops client-side over `/api/expenses/post`, so large batches are slow, fragile, and hard to resume after browser/server interruption.
- Existing logs are per-expense events only. There is no single export attempt ledger that shows queued, sending, sent, verify result, retry count, stale reason, or failure class.
- Verification already has the right safety idea: match by `OJ-EXP-*` reference first and fallback to listing/amount/date. It needs explicit confidence/status output and bulk use.
- Existing sync refresh pulls the sheet, refreshes Hostaway once, verifies sent items, and reconciles discrepancies. It is the best base for the safe repair flow, but repair needs dry-run/apply endpoints that do not blindly re-export.
- The Expenses tab has useful pieces, but it does not present the operation as an inbox grouped by actionable truth: needs review, ready, queued/sending, sent unverified, verified, failed, duplicates, archived.

## Implementation Stages

1. Normalize expense truth into canonical statuses while preserving old stored values.
2. Add tests for status mapping, stale detection, idempotency guards, and verification truth.
3. Add a durable in-memory/export-state queue persisted on each expense with attempt log entries, retry count, error class, and stale thresholds.
4. Make manual and bulk export enqueue work instead of blocking the dashboard request.
5. Add bulk endpoints for export selected, verify selected, retry failed/stale, archive verified, export log, and repair preview/apply.
6. Restructure the Expenses tab into summary cards, action bar, filters, and smart inbox groups with Arabic/English labels.
7. Add conservative safe repair workflow: dry-run first, verify existing Hostaway records by reference/key, mark verified when confirmed, requeue only selected safe items.
8. Keep max four semantic colors for status, with separate text reason chips for detailed causes.
9. Run the required `CLAUDE.md` verification commands and existing UI contract tests.
10. Commit each stage, then push once after final verification.

## Configuration

- `EXPENSE_POST_DRYRUN`: defaults to `1`; when enabled, queue and logs work but Hostaway is not written and nothing can be verified as real.
- `EXPENSE_EXPORT_WORKERS`: export worker concurrency, default `2`.
- `EXPENSE_EXPORT_MAX_RETRIES`: automatic retry attempts per expense, default `3`.
- `EXPENSE_QUEUE_STALE_MIN`: queued stale threshold, default `30`.
- `EXPENSE_SENDING_STALE_MIN`: sending stale threshold, default `15`.
- `EXPENSE_SENT_UNVERIFIED_STALE_MIN`: sent-unverified stale threshold, default `30`.
- Existing auth/config remains unchanged: `EXPENSE_INGEST_SECRET`, `EXPENSE_HOSTAWAY_PATH`, `EXPENSE_ALERT_CHANNEL`, `EXPENSE_SHEET_CSV_URL`, `EXPENSE_SHEET_POLL_MIN`.
