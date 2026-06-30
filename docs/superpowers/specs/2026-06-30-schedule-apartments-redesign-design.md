# Schedule "Apartments → who cleans" redesign

Date: 2026-06-30
Status: approved (owner)

## Problem
The Manage tab's apartments section forced the owner to hold two ideas of "apartment"
at once — a typed name AND a separate Hostaway listing to *link* it to. Every row had
6+ controls (name field, owner dropdown, link button, link status, save, delete) plus a
3-button header (import / pick / auto-link) and a picker overlay. This produced
duplicate rows (typed «الملقا 1» next to linked «MLQ 1») and confusion.

## Decision
An apartment **is** a Hostaway listing. The only per-apartment decision is **who cleans
it** (the schedule `owner_id`). Everything else (off-day coverage, channel emoji) is
already automatic from that.

Owner choices:
- Sync pulls **all** Hostaway listings.
- Changing the cleaner **auto-saves** instantly (small ✓), no per-row save button.

## The screen (replaces the apartments card in DASHBOARD_HTML `renderSchedManage`)
- Header: «العقارات (N)» + one primary button «مزامنة من Hostaway» + search.
- View toggle: «حسب الشقة» (flat list) / «حسب الموظف» (grouped by cleaner, shows balance).
- Row = apartment Hostaway name (right, RTL) + one pill on the left: employee colour dot
  + emoji + name + chevron. Tap → inline chooser of the employees as chips (+ «بدون»).
  Pick → POST owner → auto-save ✓.
- Unassigned apartments show a clear red «غير محدّد».
- Removed from this card: name field, 🔗 link button, linked/unlinked status, per-row
  save, the import/pick/auto-link trio, the picker overlay.
- Old typed leftovers (apartments with no `listing_id`) get a subtle «قديمة» tag and a
  progressive «حذف الشقق القديمة (N)» action that only appears when any exist — one click
  clears the pre-Hostaway duplicates. Never auto-deletes.

The «الموظفون» section (name · off-day · colour · emoji) stays above, unchanged — it is
set-once. The «التغطيات اليدوية» (manual coverage) card stays as-is (out of scope).

## Backend (schedule/routes.py)
- `POST /api/schedule/apartment-owner` `{id, owner_id|null}` — updates `owner_id` only
  (auto-save path). Validates the employee exists.
- `POST /api/schedule/sync` — for every Hostaway listing: insert if not already linked;
  refresh the name if linked and the Hostaway name changed. Returns `{added, updated}`.
  No deletes (keeps owner assignments safe).
- `POST /api/schedule/remove-unlinked` — deletes apartments with `listing_id IS NULL`
  (the pre-Hostaway leftovers). Returns `{removed}`.
- Existing endpoints (apartment-link, autolink, import-all, apartment save/delete) stay
  for compatibility; the new UI no longer needs them.

## Data / engine
No model change. `owner_id` is the single source of "who cleans it". `compute_day`
already distributes an apartment whose owner is off/absent. An apartment with
`owner_id = NULL` joins the pool and is auto-distributed (so «بدون» = "anyone free").

## Tests
- `apartment-owner` sets/clears owner; rejects unknown employee.
- `sync` adds missing, refreshes a changed name, never duplicates (idempotent).
- `remove-unlinked` deletes only NULL-listing rows.
- Full routine: py_compile, pyflakes, node --check erp.js, unittest, esprima parse of
  DASHBOARD_HTML, migration repro on the live DB shape.
