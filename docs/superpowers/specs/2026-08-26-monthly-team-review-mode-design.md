# Ouja Monthly Team Review Mode Design

**Date:** 2026-08-26  
**Status:** Approved design, pending implementation plan

## Goal

Give the Ouja team one simple loop for completing monthly-listing data:

1. Open an apartment.
2. Edit and save its missing information.
3. See the same apartment immediately in the customer experience.

The team uses the existing dashboard login. Customers never see incomplete apartments, draft values, internal controls, or missing advertising records.

## Staff experience

### Entry points

Authenticated `admin` and `ops` users see a staff-only gold action on monthly pages:

> وضع المراجعة: عرض كل الشقق

The action opens `/monthly/ops/preview` and preserves the current language and customer search context when possible. Anonymous visitors and other roles never receive this action in the HTML or page state.

The existing `/monthly/ops/listings` workspace keeps one primary action named:

> معاينة تجربة العميل بكل الشقق

### Apartment editing loop

Each apartment survey ends with one plain primary action:

> حفظ ومشاهدة كتجربة عميل

The action saves the current revision as a draft. A successful save opens that apartment at `/monthly/ops/preview/id/{listing_id}`. The preview reads the latest allowlisted draft over the verified source and labels every missing field. It does not require approval or a snapshot refresh.

The preview listing includes one staff-only return action:

> تعديل بيانات هذه الشقة

That action opens `/monthly/ops/listings?id={listing_id}`. The existing workspace already opens the requested apartment from this query value.

The preview catalog and recommendation cards include the same edit action, so staff can move from any incomplete apartment to its survey without searching again.

## Publication safety

Team review and customer publication remain separate states.

- Review mode includes every unique real apartment from the current trusted source.
- Draft values appear only in authenticated review mode.
- Public `/monthly` routes continue to use the published snapshot and publication gates.
- Saving a draft never approves a profile, publishes an apartment, refreshes a provider, creates a lead, or sends a message.
- The existing approval action remains available only after staff-required fields pass validation. Approval still cannot bypass price, calendar, licence, image, language, or commercial-term checks.
- WhatsApp stays disabled until Ouja supplies the approved number.

## Data flow

`CatalogService.preview_inventory()` already builds each review row from verified source data, then approved profile data, then the latest valid draft. The preview application builds a fresh in-memory generation for each request. No new database table or migration is required.

The implementation adds navigation and staff-state signals only:

1. `bot.py` confirms dashboard authentication and the `admin` or `ops` role before authoring staff-review state.
2. `monthly_public/page.py` renders the staff-only review action when the server authorizes it.
3. `monthly_public/static/monthly.js` keeps all review navigation under `/monthly/ops/preview` and adds apartment edit links.
4. `monthly_public/static/monthly_catalog.js` saves the draft, then opens the apartment review page.
5. Existing preview APIs continue to rebuild from the current catalog source and stored draft on each request.

## Team wording

The interface avoids publication terminology in the normal editing loop. Staff see:

- `بيانات ناقصة` for fields they need to complete.
- `حفظ ومشاهدة كتجربة عميل` for the normal action.
- `اعتماد بعد اكتمال البيانات` for the separate release step.

The UI never tells staff that saving a draft published an apartment.

## Error handling

- A user without dashboard access receives the existing protected response and cannot load preview APIs.
- A stale draft revision stays on the survey and shows the existing conflict recovery message.
- A failed save never navigates to the preview.
- A missing source apartment returns the existing not-found state without creating a placeholder.
- Provider availability does not affect review requests because the preview reads cached local data only.

## Verification

Automated tests must prove:

- Anonymous public pages contain no staff-review action or internal route.
- Authorized `admin` and `ops` pages receive the review action.
- Other roles do not receive it.
- Save-and-preview uses the saved listing ID and does not call approval.
- A stored draft appears in the next preview response without a snapshot refresh.
- Preview navigation never falls back to public `/monthly/search` or public listing routes.
- Customer requests make no Hostaway or pricing-provider call.
- Public publication gates still exclude incomplete apartments.

Browser checks cover Arabic and English on mobile and desktop. The review loop must work in both directions: apartment survey to customer preview, then back to the same apartment survey.

## Release and rollback

The change deploys through one push to `main` after the full monthly test suite passes. Railway restarts once. Post-deploy checks confirm the public page, protected review page, and authenticated data workspace.

Rollback removes the staff entry actions and save-to-preview navigation. Stored drafts, approved records, snapshots, analytics, and source data remain untouched.
