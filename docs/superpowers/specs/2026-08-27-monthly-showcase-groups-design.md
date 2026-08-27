# Monthly Showcase Groups

## Outcome

Ouja staff can create a named building or showcase group, assign several real
apartments to it, share one permanent public URL, and optionally activate one
fixed monthly price for customers who enter through that URL. Turning the fixed
price off keeps the URL live and restores each apartment's verified original
price. No price is written to Hostaway and no original data is deleted.

## Scope

- Add reusable showcase groups to the authenticated monthly listing-data tool.
- Add a group filter and group chips to the apartment catalog.
- Add one public group route at `/monthly/showcase/{slug}` and preserve the
  showcase context through search, listing, and WhatsApp handoff.
- Support one fixed SAR monthly rate per group, active for every month until a
  staff member turns it off.
- Keep existing monthly routes and pricing behavior unchanged outside the group
  context.

## Staff Experience

Add a `المباني والمجموعات` / `Buildings & groups` tab to
`/monthly/ops/listings`. A group record contains:

- Arabic and English name.
- Unique URL slug that becomes immutable after the first approval.
- Optional verified public image and short Arabic and English description.
- An ordered, duplicate-free list of listing IDs from the current inventory.
- Fixed monthly price in SAR.
- A separate fixed-price enabled switch.
- Revision, approval, actor, and timestamps.

The editor supports search and multi-select for apartments. It shows included,
published, and currently blocked counts before approval. Staff may save a draft,
preview it, and approve it. Enabling, disabling, repricing, or changing
apartment membership creates an audit entry. Approved group records are never
hard-deleted. The apartment table
adds a group filter and group chips. Group membership is managed from the group
record, not copied as free text into every apartment profile.

## Public Experience

The permanent URL renders a quiet-luxury Arabic-first page with an English
switch. It shows the approved group identity, the current pricing mode, and one
card per eligible apartment in the approved group. Public counts are computed
from eligible apartments, never from configured membership.

When the fixed price is enabled, the page and its apartment cards show:

`سعر خاص لهذه المجموعة: {amount} ريال شهرياً`

The page does not show discount percentages, crossed-out prices, or savings
claims. When the fixed price is disabled, the URL remains live and each card
uses the apartment's verified official price. If no apartment is eligible, the
page remains available and explains that no confirmed option is available
without claiming availability or price.

Only apartments that pass normal publication checks can appear publicly. A
blocked apartment stays assigned in the staff group so its data is not lost.

## Pricing Rules

- The group amount is one fixed monthly rate shared by every included apartment.
- It applies only when the customer carries the signed showcase context from the
  approved group URL.
- It applies to full-month duration requests while enabled. Total price equals
  the fixed monthly rate multiplied by the requested number of months.
- Four-to-six-month requests retain the approved preliminary-contract warning.
- Non-whole-month date ranges do not receive invented prorating; they require a
  verified request quote or a team confirmation.
- The group price is stored as an approved, audited customer-presentation
  override. Original engine prices remain intact and continue to serve the
  general catalog.
- Disabling the override immediately removes it from new customer responses and
  falls back to verified original prices.
- The customer request path reads only the approved cached group and snapshot;
  it makes no Hostaway or pricing-provider call.

## Context and WhatsApp Integrity

The server issues a signed, allow-listed showcase context containing the group
ID and approval revision. Public clients cannot create an arbitrary price by
editing a query string. Search and listing links preserve this context.

The lead record and prepared WhatsApp message include the group reference,
listing ID and title, dates, duration, residents, purpose, displayed price,
included and variable items, and the request to confirm availability, total,
deposit, and contract terms. The system stores the group and price references,
not the WhatsApp message body or unnecessary personal data.

If the group is repriced or its fixed price is disabled after a customer opens a
page, the next server response resolves the current approved revision. It never
honors a stale client-supplied amount.

## Data and Service Boundaries

Use focused monthly modules rather than expanding the legacy public page in
`bot.py`:

- A revision-safe showcase store with draft and approved records plus audit.
- A strict bilingual showcase contract and validation layer.
- A showcase service that resolves inventory membership and publication state.
- Thin authenticated API adapters for staff management.
- Thin public API and page adapters for the permanent URL.
- Pricing and lead context adapters that consume only server-resolved approved
  group state.

The first schema version supports many groups even though the immediate use is
one building with about eight apartments. A listing may belong to more than one
group, but one customer session carries only one active showcase context.

## Validation and Failure Behavior

Approval is refused for:

- Missing Arabic or English name.
- Invalid or duplicate slug.
- No selected apartments.
- Duplicate or unknown listing IDs.
- Enabled fixed price outside the accepted range of 1 to 1,000,000 SAR.
- Invalid image URL or mixed-language descriptions.
- Stale record revisions.

A group can be approved with blocked member apartments, but the preview must
show those blockers and the public page must omit those apartments. If group
storage is unavailable, staff see a red operational blocker and public requests
fail closed without replacing the last-known-good approved group snapshot.
Analytics failure never blocks the customer page or changes the price.

## Analytics

Add controlled monthly events for showcase view, showcase apartment impression,
showcase listing view, showcase WhatsApp click, and showcase lead creation. Each
event carries only the group ID, group revision, listing ID when applicable,
session reference, language, and price mode. Existing lead outcomes continue to
connect through the lead reference.

## Tests and Acceptance

- Contract tests for bilingual names, slug uniqueness, membership, and price.
- Store tests for revision conflicts, audit history, and no data loss.
- Service tests for public eligibility counts and blocked members.
- Pricing tests for enabled fixed price, disabled fallback, duration totals,
  four-to-six-month warning, and refusal to prorate unverified partial months.
- Security tests proving query editing cannot create a price or group context.
- WhatsApp tests proving the approved group reference and displayed price are
  included without storing the message body.
- Browser tests for staff creation, filtering, toggling, permanent URL, Arabic
  and English, mobile and desktop, empty state, and back navigation.
- A source scan proving the customer path makes no external provider call.
- Regression tests proving original apartment prices and data are never deleted
  or overwritten by showcase changes.

The feature is ready when the approved group can be managed from the catalog,
its permanent URL shows the truthful eligible apartments, the fixed rate can be
turned on and off without affecting the general catalog, and all relevant tests
and visual checks pass.
