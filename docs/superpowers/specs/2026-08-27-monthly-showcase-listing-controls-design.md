# Monthly showcase listing controls

**Approved:** 2026-08-27

## Outcome

The private building-link editor lets Ouja choose one real apartment photo as
the showcase cover and set a separate reversible monthly price for each selected
apartment. An authenticated group preview shows all configured apartments,
including incomplete ones, while the public URL continues to publish only homes
that pass the approved safety checks.

## Root cause

The existing editor stores one image URL and one group-wide price. The public
showcase correctly filters every configured apartment through the publication
snapshot. The Nuzha group therefore stores seven members but shows zero publicly
because all seven still have publication blockers. The general internal-preview
banner does not change the showcase API, so opening the public showcase from that
banner still returns the filtered public result.

## Cover selection

- Replace the free-text building-image field with a visual chooser.
- Staff first choose one selected apartment, then choose one of that apartment's
  approved real photos.
- Image options come from the authenticated cached listing record. The chooser
  does not call Hostaway or another provider.
- Store both `image_url` and `image_listing_id`. The server verifies that the
  source apartment is a group member and that the URL belongs to its approved
  image list.
- Existing stored image URLs remain intact. A legacy image without a source ID
  remains readable, so this release deletes no existing information.
- If no cover is selected, the public page keeps its existing fallback to the
  first safe visible apartment photo.

## Per-apartment monthly prices

- Store `listing_prices` as a map keyed by listing ID. Each row retains a
  `monthly_rate_sar` and an independent `enabled` switch.
- A disabled price keeps its saved amount for later reuse but does not affect the
  customer journey.
- An enabled amount applies only to that apartment when the customer arrives
  through the signed showcase link. It never changes Hostaway, the pricing
  engine, or the general monthly catalog.
- A per-apartment price may satisfy only `price_missing` for its own apartment.
  It cannot bypass licence, content, image, identity, or calendar blockers.
- If no manual apartment price is active, the home uses its verified official
  price.
- The old group-wide amount and switch remain stored for rollback and audit. New
  editor saves turn the legacy group switch off without erasing its amount.

## Internal and public behavior

- Add an authenticated URL at
  `/monthly/ops/preview/showcase/{slug}` plus a matching authenticated API.
- The internal group preview uses the existing read-only preview snapshot and
  shows every configured real apartment with missing-data chips. Contact remains
  disabled and the page is permanently labelled as an internal preview.
- The public `/monthly/showcase/{slug}` remains strict. Incomplete homes are not
  exposed publicly, and its count is computed from eligible inventory only.
- The editor offers separate actions for “Preview all selected homes” and “Open
  customer link” so the team cannot confuse the two states.

## Acceptance

- A selected apartment exposes its approved photo gallery and the chosen cover
  survives save, approval, and reload.
- Two apartments in one showcase can display and quote different manual monthly
  prices.
- Disabling one apartment price restores only that apartment's official price
  while retaining the saved manual amount.
- The authenticated preview shows all configured members and their gaps; the
  public page still omits unsafe members.
- Existing group membership, image URL, legacy price, revisions, and audit
  history remain present.
- Arabic and English controls work on desktop and mobile with keyboard-visible
  focus and no horizontal clipping.

