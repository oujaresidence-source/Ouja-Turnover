# Monthly Internal Preview Design

## Purpose

Give Ouja staff a faithful customer-journey preview that includes every real monthly inventory row, including incomplete homes, without weakening the public publication gates or deleting any existing profile, draft, approval, snapshot, or source fact.

## Approved business inputs

- Response hours: daily from 10:00 to 22:00 in `Asia/Riyadh`.
- WhatsApp: not available yet. Contact actions remain visibly blocked.
- Deposit: an indicative range of SAR 500 to SAR 2,500 in preview only. The exact amount and refund terms remain required before public publication.
- Missing listing facts must never be invented.

## Chosen approach

Add a staff-only internal preview mode beside the existing readiness workspace. It builds a temporary preview catalog from trusted source prefills plus saved staff drafts. It never writes approval records and never replaces the last-known-good public snapshot.

The public `/monthly` journey continues to read only published homes. The preview journey is available only through authenticated monthly operations routes and is marked `تجربة داخلية / Internal preview` on every screen.

## Preview behavior

- Include one preview card per real, deduplicated inventory listing.
- Use real connected photos and trusted source fields when present.
- Show `غير مكتمل` for missing content instead of generated descriptions.
- Show `السعر يحتاج تأكيد` when no verified official monthly price exists.
- Show `التوفر يحتاج تأكيد` for missing or stale calendars.
- Never show proximity claims without verified apartment and destination coordinates.
- Never show unverified ratings, review counts, licences, amenities, or service claims.
- Disable WhatsApp and lead creation until a valid number is configured.
- Keep the matcher usable with verified facts; homes missing a requested fact may appear only as clearly labelled alternatives, never as exact verified matches.

## Data preservation

The preview path is read-only with respect to catalog data. It may read source rows, approved profiles, and current drafts, but it cannot call save, approve, refresh, or public snapshot replacement methods. Existing data is preserved byte-for-byte.

Automated regression tests will take store snapshots before and after preview generation and assert that profiles, settings, places, audit entries, and public snapshot identifiers are unchanged.

## Settings handling

Working hours are represented as seven daily intervals from 10:00 to 22:00 in Riyadh time. The deposit range is preview metadata, not an official public deposit term. Missing WhatsApp, exact deposit/refund terms, payment methods, and four-to-six-month routing remain red launch blockers.

## Interface

The readiness workspace gets one clear action, `معاينة رحلة العميل`, plus a short explanation that previewing does not publish. The preview reuses the established Arabic-first monthly interface and cream/gold Ouja tokens, adding a persistent restrained banner and visible missing-data chips. It does not add decorative motion or a separate visual system.

## Verification

- Unit test: preview includes incomplete real homes and labels missing facts.
- Safety test: preview generation does not mutate store records or public snapshot state.
- Contract test: unauthenticated preview endpoints are rejected.
- Public regression: `/api/monthly/search` still returns only published homes.
- Settings test: response hours are daily 10:00–22:00; WhatsApp remains blocked.
- Browser checks: Arabic and English, desktop and mobile, matcher, browse, listing, missing price, missing calendar, and disabled WhatsApp.

## Out of scope

- Publishing incomplete homes to the public catalog.
- Inventing or mass-generating listing facts.
- Changing production configuration or deploying without a separate verified release step.
