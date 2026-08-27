# Monthly showcase hero image design

**Approved:** 2026-08-27

## Outcome

Place one wide, centered hero image at the top of every approved monthly showcase, before the apartment cards. The image makes the private building link visually engaging without adding an unverified property claim.

## Image source order

1. Use the approved showcase image when the team has provided one.
2. Otherwise use the first safe public image from the first customer-visible apartment in the showcase.
3. If neither source exists, keep the current text-only hero. Do not add a stock image, placeholder, generated building photo, or broken image frame.

The fallback reads only the already prepared public showcase response. It does not call Hostaway or another provider during the customer request.

## Layout

- The image spans the showcase content width and sits above the group title and description.
- Use a restrained landscape ratio with the full image visible through a centered crop.
- Keep the group title and price strip outside the photo for reliable contrast and Arabic readability.
- Preserve the existing quiet ivory, green, and bronze visual system.
- On mobile, the image remains full width with a shorter landscape ratio and no horizontal overflow.

## Accessibility and reliability

- The image receives a localized description derived from the approved showcase name.
- Invalid or unsafe image URLs are ignored.
- A failed image load hides only the media area; the title, apartments, pricing, and navigation remain usable.
- Reduced-motion behavior is unchanged because the hero adds no required animation.

## Verification

- Unit-test the approved group-image priority, real apartment-image fallback, and unsafe/missing-image state.
- Run the monthly showcase and public-content test suites.
- Inspect Arabic and English at desktop and mobile widths.
- Confirm no broken frame, clipping, horizontal overflow, unnamed controls, or console errors.
