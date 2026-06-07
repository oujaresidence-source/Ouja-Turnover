# Ouja Financial Brain (المركز المالي) — Stage 0 Discovery & Plan

> Import-first finance control layer around Daftra. NO fake data · NO auto-post to Daftra ·
> Decimal money · masked secrets · bilingual RTL · reuses existing patterns. Additive only.

## A. Existing architecture (audited in `bot.py`)
- **Finance today:** `view_finance` + `view_expenses` (Expenses V4 `_exp4_*`) + `view_weekly`; builders
  `compute_owner_report`/`build_owner_report`/`_finance_aggregate`; owner+cleaning registry
  (`_owner_registry`); editable statements (`_finance_adjust`, per-line overrides + `_finance_audit`);
  server PDF. Money helpers `money2()` (JS) + `_money2`/2-dp (added for line items).
- **Expense intake:** Google-Sheet CSV (`EXPENSE_SHEET_CSV_URL` → `_exp_fetch_sheet`/`_exp_ingest`),
  `OJ-EXP-XXXX` refs (`_new_exp_ref`-style), V4 lifecycle (captured→approval→export→verified) with
  Hostaway `/expenses` writeback + read-back verify (`_exp4_*`). **Reuse the verify/idempotency pattern.**
- **Roles:** `_default_perms(role)` for `admin|ops|viewer` (L10752); `_user_create`; per-tab perms;
  nav `adminOnly` gated by `D.me.user.role`. `_dash_auth`/`_req_actor`. → **extend with `accountant`.**
- **Discord:** `_post_system_escalation(title, detail, severity)` → #escalations. **Reuse for ≥3000 SAR.**
- **Persistence:** module-level `_load_json("x.json",default)` + `_save_json` + `persist_state()`/`load_state()`.
- **i18n:** `T={ar:{…},en:{…}}`, `t()`; NAV `{id,ic,tk,badge?}` + `NAV_CATS` (`cat_finance` ids
  `['expenses','finance','weekly']`); `go()` dispatch; `_USER_TABS`.
- **Daftra:** **none exists.** New connector required. **I cannot reach Daftra from this dev env**
  (no creds, no network) → connector is written + fail-graceful; real import/post is **deploy-verified**.

## B. Reuse vs new
**Reuse:** `_load_json/_save_json/persist_state`, `_dash_auth/_req_actor`, role/perms system (extend),
`_post_system_escalation` (≥3000 alerts), the Sheet intake + `OJ-EXP` + V4 verify/idempotency pattern,
`money2`/Decimal-2dp display, NAV/`NAV_CATS`/`go()`/`T.ar`+`T.en`, drawer/empty-state/skeleton patterns,
openpyxl (already a dep, used by finance/expenses) for Excel parsing.
**New (`_fb_*` namespace):** Daftra connector, bank Excel parser, contract-profile importer, financial
inbox, approval workflow, journal-draft + verify, profitability, monthly-close, mapping screens, the
9 JSON stores, `accountant` role, Decimal helpers, masking helpers.

## C. Daftra connector (`_daftra_*`) — READ-FIRST, no auto-post
- Env: `DAFTRA_BASE_URL`, `DAFTRA_API_KEY` (never logged/exposed), opt `DAFTRA_COMPANY_SLUG`,
  `DAFTRA_IMPORT_START_DATE`. Auth header `APIKEY: <key>` (confirm against the live account on deploy).
- `_daftra_get(path)` with timeout + graceful errors (no stack traces to UI, no key in logs).
  `_daftra_test_connection()`. Importers (read): chart of accounts, cost centers/projects,
  suppliers, customers, expenses, incomes, journal entries, treasuries — **each fail-graceful**
  (endpoint may not exist → record `sync_error`, never crash, never fake).
- **Idempotent:** upsert by `(source_type, source_id)`; store `source_payload`, `source_hash`
  (checksum) → conflict detection on change. `finance_import_runs` tracks each run.
- **Posting:** built as **draft → preview → review → (Faisal if needed) → explicit Post → read-back
  verify**. Default **DISABLED** (`DAFTRA_POST_ENABLED` flag, off). "Verified in Daftra" badge ONLY
  after read-back match (id+amount+date+ref). Statuses: not_imported/imported/draft/ready/posting/
  posted/verification_pending/verified/failed/needs_fix. Never show "مرحّل" unless posted+verified.

## D. Data model (9 entities → JSON stores via existing pattern)
`finance_import_runs.json` · `finance_external_records.json` (Daftra mirror) ·
`finance_contract_profiles.json` · `finance_bank_transactions.json` · `finance_ledger_entries.json`
(canonical) · `finance_daftra_mappings.json` · `finance_approvals.json` · `finance_audit_log.json`
(append-only) · `finance_card_mappings.json`. Loaded at import, saved on write (like `_finance_adjust`).
Money stored as exact strings + parsed with **Decimal** (`_fb_money(x)` → `Decimal`, 2-dp, never float).

## E. Roles & permissions (extend `_default_perms`)
Add **`accountant`**: finance import/classify/approve <3000/prepare drafts; NOT ≥3000, NOT posting-enable.
`admin` (Faisal/CEO): all + approve ≥3000 + override close + enable posting + mappings.
`ops`: submit/view own expense status only — **no profitability, no bank detail, no edit after submit.**
`viewer`: read-only summaries. No role ever sees raw API keys / IBAN / full card numbers (masked).

## F. Money + masking
`_fb_money` Decimal (preserve halalas, 9.50 stays 9.50); `_fb_mask_iban`/`_fb_mask_card`/`_fb_mask_key`
(show last 4 only). Bank account/IBAN/API key never in UI or logs.

## G. Stages (commit each; ONE push at end)
S0 plan (this doc). S1 nav + 12 sub-sections shell + setup checklist + empty states + i18n.
S2 data stores + import-run + audit + Decimal/masking helpers + status enums + `accountant` role.
S3 Daftra read-only connector + import + counts/status UI + mapping skeleton. S4 contract Excel
importer (map→preview→validate→health chips, no guessing). S5 Al Rajhi bank Excel parser (Decimal,
dup-detect, mask, auto-classify basics, card last4 + card-map screen). S6 Financial Inbox + approval
workflow (≥3000→Faisal + Discord) + audit + no-edit-after-submit + void-not-delete. S7 journal drafts
+ verification architecture + Sync Log (post DISABLED by default). S8 Unit + Company profitability
(coverage/confidence, no fake revenue) + Monthly Close preview (close disabled until safe). S9 polish,
permissions QA, verification gate.

## H. Risks / manual steps (honest)
- **Daftra is untestable from this dev env** → connector correctness for real endpoints is confirmed
  only after deploy with real creds; exact endpoint paths/auth header must be confirmed against the
  live Daftra account. Posting stays **disabled** until the owner confirms endpoints + flips the flag.
- Hostaway revenue is **architecture-only** this pass (read-only later); profitability shows
  "revenue source not connected" until then — never faked.
- `Book 8.xlsx`/bank file are **not in the repo** → importers are generic; owner uploads via UI.

## I. Verification (CLAUDE.md routine + finance-specific)
`py_compile` · `pyflakes` · esprima all embedded pages · {}/() balanced + backticks even · i18n parity
(every new key in T.ar+T.en) · no backslash escapes in embedded JS · Decimal smoke (9.50→9.50) ·
masking smoke · empty-state smoke · permission-gate smoke · missing-Daftra-env smoke.
