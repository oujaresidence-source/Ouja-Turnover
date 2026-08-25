# Expenses V2 Root-Cause Audit

Date: 2026-06-03

## What is broken

The current Expenses tab mixes four different ideas into one screen: review queue,
export queue, Hostaway verification, and repair. That makes the operator see
`queued`, `stale pending`, `pending too long`, `failed`, and green-looking pipeline
steps without a clear answer to the real question: is this expense actually in
Hostaway?

The most important bug is in the repair flow:

- `_exp_repair_preview_rows()` labels rows with a stored `hostaway_ref` as
  `verify_first`.
- `_api_expenses_repair_apply()` verifies those rows, but if Hostaway verification
  does not find them, it still calls `_exp_queue_for_export(...)`.
- `_exp_export_one()` then refuses to export those same rows when a real
  `hostaway_ref` exists, because duplicating a possible Hostaway expense would be
  unsafe.
- Result: the UI says rows were queued, but the worker blocks them as
  `retry_blocked_sent_unverified`, and they fall back to `stale_pending`.

That explains the screenshot behavior: “Apply selected repair” can report many
queued rows while the underlying issue is unchanged.

## Why expenses become stale pending

`queued`, `sending`, and `sent_unverified` become `stale_pending` after the configured
thresholds when no worker/verification finishes them:

- queued older than `EXPENSE_QUEUE_STALE_MIN`
- sending older than `EXPENSE_SENDING_STALE_MIN`
- sent/unverified older than `EXPENSE_SENT_UNVERIFIED_STALE_MIN`

For rows with a real `hostaway_ref`, stale usually means: the dashboard believes a
Hostaway expense id exists, but the current bulk Hostaway fetch/matcher did not
confirm it.

## Does retry export or only queue/verify?

Retry queues work. The worker validates and exports only when the row is safe:

- Rows without a real Hostaway ref can export after validation.
- Rows with a real Hostaway ref verify first.
- If verification fails and the ref is a real Hostaway id, the worker blocks export
  to avoid duplicates.

So retry can look like an export action in the UI, but for real-ref rows it becomes a
verify-and-block action.

## Hostaway/API findings from code

The configured endpoint is `EXPENSE_HOSTAWAY_PATH`, defaulting to `/expenses`.

The export payload currently includes:

- `listingMapId`
- negative `amount`
- `expenseDate`
- `date`
- `categoryName`
- `concept`
- `name`
- `reference` containing `OJ-EXP-...`
- `description` including the Ouja reference and metadata
- `currency: SAR`

Hostaway send errors are stored on the expense as `error` and `error_class`.
However, sent rows with existing Hostaway refs usually do not call `api_post` again,
so they do not surface a new Hostaway validation error. They fail at verification.

## Verification gap

`_exp_verify_in_hostaway()` verifies by:

1. fetching a paginated list from `EXPENSE_HOSTAWAY_PATH`
2. matching by the Ouja reference inside the returned JSON
3. falling back to `(listing, amount, date)`

Risks:

- The bulk fetch is capped (`max_pages=10`, page size 100), so it may miss older or
  differently sorted Hostaway expenses.
- Existing Hostaway expenses may not contain the `OJ-EXP-...` reference if they were
  created before the reference field was added.
- Matching by `(listing, amount, date)` is conservative, but it can miss records if
  Hostaway stores date, listing id, category, or amount shape differently.
- The code does not currently attempt a direct fetch by stored Hostaway expense id
  before falling back to bulk search.

Because of this, a stored real `hostaway_ref` can remain “sent but not verified”
even if the expense exists in Hostaway.

## Duplicate detection findings

Local duplicate detection happens before export using listing id, amount, category,
and nearby date. Reconciliation also flags duplicate local keys. The old repair UI
does not clearly separate:

- local duplicate
- Hostaway duplicate
- real Hostaway id not found in current fetch
- safe missing expense with no Hostaway ref

That is why the operator cannot tell whether duplication is blocking export.

## Sheet parsing findings

Google Sheet parsing is idempotent by a stable `gs-...` submission id made from row
fields. The sheet diagnostics already track fetch status, headers, mapped columns,
rows parsed, data rows, and created rows. Sheet parsing can still produce Needs
Review when amount, date, category, receipt, or apartment mapping is incomplete.

No evidence in code shows the stale-pending loop is primarily caused by sheet parsing;
it is mostly caused by repair/verification semantics around existing Hostaway refs.

## Queue/worker findings

The queue is in-process. It persists queued/sending state on the expense, but the
actual deque is memory-only. After a Railway restart, old queued/sending rows become
stale and require a dashboard action to resume. That is acceptable only if the UI
shows it as a stuck queue with an exact reason, not as “pending too long”.

## V2 implementation decisions

Expenses V2 must:

- keep the old endpoints available as fallback
- make `Verified in Hostaway` possible only after re-fetch confirmation
- replace `Safe repair` with dry-run-first `Reconcile & Repair`
- never queue rows with real Hostaway refs as if they are safe exports
- show source states separately for Sheet, Dashboard, and Hostaway
- show a plain reason and recommended action for every non-verified row
- add split parent/child helpers before export, with no Hostaway write during split
- add diagnostics CSV/logs so the operator can see whether the issue is mapping,
  duplicate, Hostaway API, verification matching, sheet parsing, or queue stuck

## Safe workflow for current stuck expenses

For rows with a real `hostaway_ref`:

1. Re-fetch Hostaway.
2. Try direct id/reference matching.
3. If matched, mark Verified in Hostaway.
4. If not matched, mark Sent, Not Verified with reason.
5. Do not re-export automatically.

For rows without a real `hostaway_ref`:

1. Validate required fields.
2. Detect local/Hostaway duplicates.
3. If safe, export with the `OJ-EXP-...` reference.
4. Re-fetch Hostaway.
5. Mark Verified only if found.
