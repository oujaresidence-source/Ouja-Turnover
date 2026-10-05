# «حساب المالك» — owner-account billing (first building: عمارة النزهة)

Date: 2026-10-05 · Status: approved by the owner in a brainstorming session (answers quoted below).

## Why

Owner «ابو فهد عبدالحمن الخطيب» (8 units, Al-Nuzha) registered for VAT. His 8 listings were
duplicated under HIS Airbnb account (names suffixed «-O», live since 2026-09-13…19). Airbnb now
pays HIM. For these listings the money flows the opposite way to every other owner: Ouja does not
pay a net — Ouja **bills** him. Every VAT-registered owner will follow (the «العقود» contract module
already forces VAT owners onto the owner's account), so this is built as a general mode with this
building as its first entry.

## Decisions (owner's answers)

| # | Question | Answer |
|---|---|---|
| 1 | What does Ouja charge? | **Same deal as before**: 18% of the Airbnb payout, cleaning on Ouja, expenses at cost, +15% VAT on Ouja's fee only |
| 2 | Transition months | **Two separate documents**: the old statement keeps running on the OLD listings; a new claim covers the «-O» listings |
| 3 | Which document carries an expense? | **By date**: before the unit's switch date → old statement; on/after → the claim |
| 4 | Switch date | **Per unit = first check-in on its «-O» listing**; 102B fills itself on its first booking |
| 5 | When is a claim issued? | Day 1–5 of each month, for the previous month; owner pays within 10 days (contract) |
| 6 | PDF look | **Full statement** (per-unit table → bookings → expenses → total due) |
| 7 | Tab | **Month board**: draft → ready → approved → sent → paid (+ overdue) |
| 8 | Tax invoice | Issued in **Daftra**; its number is typed in; **no approval without it**. Our PDF is «كشف حساب ومطالبة مالية», never «فاتورة ضريبية» |
| 9 | Delivery | Download PDF + a WhatsApp button with a prefilled message; a human sends |
| 10 | Build approach | On top of the existing statement engine, in an isolated module |

## Money rules (per unit, per month)

* Bookings: every confirmed booking on the unit's **«-O» listing** whose check-in falls in the month.
  The listing decides whose money it was, so bookings are NOT filtered by the switch date.
* Income = `build_owner_report(new_lid, …)` with `adjust={}` (no legacy edits) and cleaning "ours" —
  i.e. the same proven payout rules: Airbnb payout − refund; cancelled rows never auto-count.
* `fee = round2(income × 18%)`, `vat = round2(fee × 15%)` — rounded **per unit**, totals are sums,
  so the PDF table always adds up to the halala.
* Expenses: posted ledger expenses (`_exp_posted_to_hostaway`) tagged to the unit's **old OR new**
  listing, dated in the month and **on/after the unit's switch date**, at cost (no fee, no VAT).
* Manual lines (reason required, who/when recorded):
  * `income` — e.g. a retained cancellation payout; carries fee + VAT.
  * `expense` — at cost.
  * `credit` — in the owner's favour, at cost (subtracted).
* **Total due = Σ(fee + vat) + manual-income (fee + vat) + expenses + manual expenses − credits.**
  A negative total is printed as owed TO the owner.

### Blockers (approval refused, shown on the board)

* A booking with no Airbnb payout (`missing_payout`) — never guessed.
* A non-Airbnb booking on an «-O» listing — whose money it was is unknown («يحتاج قرار»).
* Degraded Hostaway pull (truncated data).
* Month not finished; Daftra invoice number missing.

## Effect on the old statement

* `build_owner_report` skips ledger expenses on the 8 **old** listings dated on/after that unit's
  switch date (one guarded hook, `_ownerbill_expense_moved`). No such expense exists today
  (checked live 2026-10-05), so no published number moves.
* The 8 old registry rows get their listing id **pinned** (one-time marked migration). Today 7 of 8
  resolve by name, and «101b» also matches «101B-O».
* «-O» listings are never added to the owner registry; the tab shows a guard if any registry row
  ever resolves to one.

## Workflow & storage

* Store `ownerbill.json` (STATE_DIR): per-building settings (bank text, phone, display name,
  WhatsApp template), per-unit switch dates (`auto` or edited with a reason), per-month records
  (manual lines, Daftra no., status, frozen versions, sent/paid stamps, audit).
* Status: `running` (month not over) · `needs_review` (blockers) · `ready` · `approved` (snapshot vN
  frozen, PDF) · `sent` (due = sent + 10 days) · `paid`; `overdue` is derived. «إعادة فتح» (admin,
  reason) returns an approved month to ready and keeps every version.
* Access: ERP finance roles (admin/accountant) via `_guarded`. Reads Hostaway only. Writes nothing
  to Hostaway, Airbnb or Daftra and sends nothing on its own.

## Surfaces

* ERP «الملاك» page: a card «حسابات على حساب المالك» → `#owners?bill=nuzha`.
* Building screen: guards strip, switch dates, month board, month detail (units table, bookings,
  excluded/cancelled, expenses, manual lines, Daftra no., actions), audit trail.
* PDF (fpdf2, the house statement renderer's font + shaping): «كشف حساب ومطالبة مالية», claim no.
  `OJ-NZH-YYYY-MM`, version, per-unit table, bookings per unit (guest initial only), expenses,
  manual lines, totals box, due date + bank text, Daftra invoice no., the not-a-tax-invoice note.
  Unapproved months print a «مسودة — غير معتمدة» band.

## Testing

`tests/test_ownerbill.py`, synthetic Hostaway rows through the real engine: per-unit rounding,
VAT only on the fee, expenses by date across old/new listings, cancelled excluded, missing payout
and non-Airbnb block approval, Daftra gate, frozen version survives a Hostaway change, sent→due
date→overdue, reopen keeps versions, old-statement hook moves only post-switch expenses, pin
migration, PDF renders (Arabic font) for draft and approved.
