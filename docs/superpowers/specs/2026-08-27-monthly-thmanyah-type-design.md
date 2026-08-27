# Ouja Monthly Thmanyah Typography Design

## Outcome

Replace the monthly-rental experience's Apple/system and IBM Plex-first typography with the supplied Thmanyah family while preserving every existing apartment record, customer-flow decision, text size, emphasis, and bold hierarchy.

## Scope

- Public monthly customer pages: `/monthly`, matcher, catalog search, listing pages, and the authenticated customer preview.
- Monthly operations pages: `/monthly/ops` and `/monthly/ops/listings`.
- Out of scope: the broader Ouja dashboard and unrelated public products in `bot.py`.

## Typography decision

- Public customer headings use **Thmanyah Serif Display** to add a controlled editorial-luxury character.
- Public customer body copy, subtitles, controls, prices, metadata, and navigation use **Thmanyah Sans** for screen readability.
- Operations and listing-data pages use **Thmanyah Sans throughout**, including headings, because they are dense working tools where consistency and scanning speed matter more than display character.
- Existing bold roles stay bold. Regular, Medium, Bold, and Black files cover the current 400, 500/600, 650/700/750, and 800 weight roles without browser-synthesized bold.

## Loading and safety

- Keep the original ZIP untouched.
- Copy only the required WOFF2 files into a dedicated monthly static-font directory.
- Serve only explicit allow-listed, fingerprinted font routes with the correct `font/woff2` content type and immutable caching.
- Use `font-display: swap` and a same-origin stylesheet; no Google Fonts or third-party runtime dependency.
- Preload only the regular Sans file used above the fold.
- Preserve system stacks as fallbacks so pages remain usable if a font request fails.

## Legal decision record

The attached license was reviewed and its web-distribution restriction was explained before implementation. The user explicitly instructed the team to proceed with the requested push after that warning. No claim is made that the font owner approved Ouja's hosting method.

## Proof

- Contract tests verify the page links, preload, route allow-list, immutable caching, WOFF2 signatures, font-family roles, and exact weight sources.
- Existing monthly unit, contract, and integration suites remain green.
- Public CSS remains independent of third-party font hosts.
- Browser checks cover Arabic and English on mobile and desktop, including loading, headings, body copy, forms, prices, and the dense listing-data table.

