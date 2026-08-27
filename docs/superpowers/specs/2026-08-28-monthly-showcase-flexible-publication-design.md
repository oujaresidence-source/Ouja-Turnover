# Flexible publication for monthly showcases

**Approved:** 2026-08-28

## Outcome

An approved monthly showcase can display a selected apartment on its public
customer URL without requiring every descriptive field to be complete. The
minimum publication gate is reduced to three verified facts: a valid advertising
licence, at least one real apartment image, and an approved monthly price for
that apartment. Missing optional content no longer makes a whole building link
look empty.

This change applies only to approved showcase links such as
`/monthly/showcase/nuzha`. The general monthly catalog and matcher keep their
existing publication rules.

## Approaches considered

1. **Flexible public showcase — selected.** Publish homes that pass the minimum
   gate, omit unsupported details, and clearly defer unknowns to the Ouja team.
   This gives customers a real external experience without inventing claims.
2. **Externally accessible test link.** Keep the public link strict and expose an
   unlisted preview. This is useful for internal review but does not solve the
   empty customer link.
3. **Keep the full publication gate.** This has the strongest content controls
   but leaves the approved building link empty until every field is complete.

## Minimum publication gate

A selected showcase apartment may appear publicly only when all three checks
pass:

- Required advertising information exists and the licence is not expired.
- At least one approved real image is available from the cached listing data.
- The apartment has either an enabled showcase monthly price or a verified
  official monthly price.

The showcase remains backed by the cached snapshot. Customer requests never
call Hostaway, a pricing provider, or another external service.

## Optional information

The following gaps become warnings instead of publication blockers for an
approved showcase:

- Arabic or English marketing description.
- Arabic or English display title.
- Bedroom, bathroom, neighborhood, amenity, service, rating, and review detail.
- Current calendar coverage or freshness.

Unknown information is never guessed. The public card and listing page omit an
unsupported section or use neutral copy such as "يؤكدها فريق عوجا". A missing
Arabic title uses a neutral unit label with the real listing ID rather than an
unverified translation. Missing calendar data is presented as availability that
must be confirmed, never as available.

## Price behavior

- An enabled per-apartment showcase rate is the approved monthly price for that
  apartment inside the signed showcase journey.
- The price applies only to that apartment and showcase; it does not update the
  pricing engine, Hostaway, or the general monthly catalog.
- If the manual rate is disabled, the home needs a verified official monthly
  price to remain visible.
- No percentage discounts, crossed-out prices, or invented reference prices are
  introduced.

## Customer experience

- The existing permanent showcase URL remains unchanged.
- The public count reflects only selected apartments that pass the three-item
  minimum gate.
- Cards show the real image, safe title or listing reference, monthly price, and
  only verified supporting facts.
- Missing optional facts do not produce blank labels, placeholders, or false
  claims.
- The apartment page states that availability and any missing commercial detail
  will be confirmed before commitment.
- WhatsApp remains disabled when the configured number is absent.

## Team experience

- The showcase editor distinguishes three states: published, published with
  missing optional details, and blocked by a minimum requirement.
- Each blocked apartment shows which of the three minimum requirements is
  missing.
- Existing listing data, approved profiles, prices, group membership, images,
  revisions, and audit history remain unchanged.
- Completing optional information later improves the live page automatically;
  it does not require recreating the showcase URL.

## Testing

- A licensed apartment with a real image and enabled showcase price appears even
  when descriptions, amenities, ratings, calendar data, and room details are
  missing.
- Missing or expired advertising information still blocks publication.
- Missing images still block publication.
- Missing both manual and official monthly price still blocks publication.
- Disabled manual price falls back only to the apartment's verified official
  price.
- Public Arabic and English pages omit unsupported claims and preserve correct
  direction.
- Public counts match the relaxed eligible set without duplicating apartments.
- The customer request path performs no external provider calls.

## Rollback

The change is isolated to showcase eligibility and presentation. Reverting the
feature restores the previous strict showcase gate without deleting or rewriting
any listing or showcase data.
