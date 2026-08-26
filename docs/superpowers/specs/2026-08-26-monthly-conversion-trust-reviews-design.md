# Ouja Monthly Conversion, Trust, and Reviews Design

**Date:** 2026-08-26  
**Status:** Approved design; implementation pending  
**Scope:** Upgrade the existing Ouja monthly-rental customer journey and listing operations workspace. Preserve current URLs and reuse the existing monthly modules and real Ouja data.

## 1. Outcome

The monthly product must feel like a carefully managed Riyadh hospitality service, not a discount marketplace. It must help guests with different price sensitivities find a suitable home without asking for an exact budget, explain the value behind the official price, and prove trust with listing-specific public reviews.

The upgrade has three connected workstreams:

1. Conversion and price confidence: qualify price sensitivity respectfully and explain value before the WhatsApp handoff.
2. Verified review proof: publish a complete rating summary and the latest ten public reviews for the same listing.
3. Full-journey polish and operations: improve every public state and make the internal listing workspace fill itself from existing sources while preserving all source data.

## 2. Approved Product Decisions

### 2.1 Price sensitivity

Do not ask for an exact budget or budget range. Add one matcher question:

> وش الأهم لك في ترتيب الخيارات؟

Answers:

- 💎 أفضل تجربة
- ⚖️ أفضل توازن بين القيمة والسعر
- 💰 الأقل سعرًا الذي يناسبني

The answer changes ranking only. It never changes the official price.

Availability, publication eligibility, resident capacity, dates, and verified fit remain hard gates. Price priority only orders homes that already pass those gates. Expensive homes must never rank first merely to increase revenue.

### 2.2 Reviews

Each listing page shows:

- The verified aggregate rating and count from all eligible reviews linked to that listing.
- A short category or topic summary only when supported by verified source data.
- The latest ten eligible public review texts for the same listing, sorted newest first.

Do not select only positive reviews. If fewer than ten eligible texts exist, show all of them. If no listing-specific text exists, say so. A company-wide review section may be shown only when labeled clearly as “تجارب ضيوف عوجا,” never as reviews of the selected listing.

### 2.3 Emoji style

Use emojis functionally and quietly:

- One emoji may accompany human matcher choices, trust chips, and friendly empty states.
- Emojis must always accompany text and never be icon-only.
- Do not use emojis inside prices, totals, deposit terms, payment methods, advertising information, or legal copy.

### 2.4 Data preservation and staff work

The system fills listing records from existing sources. Staff confirm gaps and conflicts rather than re-entering known facts.

Source records are immutable. Staff edits are stored as versioned overlays with an audit trail. A refresh must not delete source values or erase an approved staff override. When refreshed source data conflicts with an override, the workspace shows both values and asks for confirmation.

### 2.5 Preview and public publication

- Internal preview shows every real inventory home, including incomplete homes, with a prominent internal-preview banner and precise missing-data reasons.
- The public catalog shows only homes that pass the approved publication rules.
- Incomplete homes are never deleted. They remain visible in the operations workspace until completed.

## 3. Research Basis

There is no reliable universal public leaderboard for the “highest-converting accommodation website.” OTAs define and measure conversion differently. Ouja must benchmark proven interaction patterns and measure its own funnel.

The design uses these external findings as directional evidence:

- Baymard’s accommodation research finds that unclear total costs, fee breakdowns, and weak homepage booking focus create abandonment. Ouja will show one official monthly price, the total for selected dates, and a clear included-versus-variable breakdown.
  - https://baymard.com/ux-benchmark/collections/travel-accommodations
  - https://baymard.com/blog/travel-site-ux-best-practices
- Expedia’s 2025 Traveler Value Index reports that low price and positive reviews are both leading hotel value considerations. Ouja will support price-sensitive ordering without weakening review and service proof.
  - https://partner.expediagroup.com/content/dam/unified/partner/documents/reports/2025-reports/traveler-index-value-2025_snapshot_hotels_us-en.pdf
- Medill Spiegel Research Center shows that reviews materially affect purchase likelihood, especially for higher-priced items, and that perfect-looking review profiles can reduce credibility. This is e-commerce evidence, not a direct hospitality conversion forecast; Ouja uses it only to justify showing complete, non-cherry-picked review evidence.
  - https://spiegel.medill.northwestern.edu/how-online-reviews-influence-sales/
- Airbnb’s trust pattern combines overall rating, category ratings, recency, and reliability. Airbnb’s total-price display also supports showing the total before checkout decisions.
  - https://www.airbnb.com/help/article/3495
  - https://news.airbnb.com/airbnb-is-introducing-total-price-display-and-updating-guest-checkout/
- Blueground is the closest monthly-stay reference for move-in-ready homes, flexible terms, and high-touch service. onefinestay is a useful luxury reference for curation, service, and trust proof. Ouja will adapt those principles to its verified Riyadh inventory rather than copy their appearance or claims.
  - https://www.theblueground.com/
  - https://www.onefinestay.com/?lang=en

## 4. Customer Journey

### 4.1 Homepage

Keep the hybrid entry:

- Primary: “ساعدني أختار”
- Secondary: “تصفح كل البيوت”

The page must explain the product before presenting prices: furnished monthly homes, managed by Ouja, with an official price for selected dates. Add a restrained trust strip using only supported facts, such as verified reviews, ready access, managed service, and customer support.

Do not show an inventory count unless computed from the current eligible public snapshot. Do not show discounts, crossed-out prices, maximum discount prompts, or fabricated scarcity.

### 4.2 Adaptive matcher

Keep one question per screen, automatic progression, persistent back navigation, and the approved purpose branches for work, family, treatment, and visits.

Add the price-priority question after the space requirement and before date confirmation. Explain that it affects ordering, not the price.

The completed matcher sends one stable preference contract containing purpose, residents, sleeping requirements, dates, flexibility, neighborhood or important place, and price priority.

### 4.3 Results

Results are divided into:

1. Best three matches.
2. Other strong options.
3. Complete eligible catalog.

Each best match includes:

- Why it fits, based only on verified answers and listing facts.
- One useful tradeoff when the data supports it.
- Verified rating and review count when available.
- Official monthly price and total for the selected duration when the quote is valid.
- A direct route to the listing page.

For the “lowest suitable” priority, sort eligible homes by official total price after hard-fit checks. Homes without an official price are not eligible for public ranking. Internal preview may show them with a missing-price warning.

Empty and near-match states must explain which constraint prevented a full match. They may offer verified alternate dates or homes, but must not claim availability that the snapshot cannot prove.

### 4.4 Browse all homes

Keep filters for dates, duration, residents, bedrooms, neighborhood, and approved important places. Add rating and verified amenity controls only when the source supports them.

Price ordering is available only after dates are selected and official totals exist. Maps and travel-time language require verified coordinates or approved distance data. The closest-five display excludes universities as approved.

### 4.5 Listing page

The Arabic-first listing page uses this order:

1. Real Ouja photo gallery.
2. Arabic title, English switch, verified rating, review count, and key facts.
3. “Why this fits” explanation when the guest arrived from matching.
4. Structured story and grouped verified amenities.
5. Location proof and the closest five approved places.
6. Review summary and latest ten reviews.
7. Official price card and WhatsApp handoff.
8. Required advertising and license information.

The page must not expose raw English descriptions on the Arabic view. Missing translations appear as an explicit internal-preview issue, not as public mixed-language content.

### 4.6 Price card

For a valid listing and dates, show:

- Official monthly rate.
- Total for the selected duration.
- Internet and maintenance treatment from the approved listing or global commercial terms.
- Listing-specific utility handling.
- Optional cleaning terms.
- Exact required deposit and refund terms when approved.
- Configured payment methods.

The approved deposit policy range is SAR 500–2,500. A public listing must have an exact approved amount within that range; otherwise publication is blocked. Internal preview may show the range and the missing-exact-amount warning.

For four-to-six-month stays, show exactly:

> سعر مبدئي. يؤكد فريق عوجا نوع العقد والشروط قبل الالتزام.

Value explanation focuses on verified furnishings, included services, management, maintenance, and support. It must not use discount percentages or unverified market comparisons.

### 4.7 WhatsApp

The customer reviews and sends the prepared message; the website never sends automatically.

The message contains the approved lead reference, listing ID and title, dates and duration, residents, purpose, selected area or place, price shown, included and variable items, and a request to confirm availability, total, deposit, and contract terms.

Working hours are 10:00–22:00 Asia/Riyadh. During working hours, show the approved 30-minute response promise. Outside working hours, show the next response period.

The WhatsApp number remains a required configuration value. Until it is supplied, the public and preview interfaces show a clear unavailable state and the operations page shows a red blocker. No placeholder number is permitted.

## 5. Review Data Design

### 5.1 Existing sources

The current repository already contains relevant review infrastructure:

- `bot.py` has the background Hostaway review fetch and normalized review fields.
- `reviews_seed.json` contains the historical review seed.
- `reviews_insights.json` contains historical per-listing category insights.

The public customer request path must not call Hostaway or another provider. Review data is prepared during background refresh and stored in the last-known-good monthly snapshot.

### 5.2 Eligibility

A public review is eligible only when:

- `is_public` is true.
- It has a non-empty public review text for text display.
- Its listing ID exactly matches the selected listing.
- Its source record and date are valid.
- Its rating is in the normalized valid range.
- It contains no known private field in the public payload.

Aggregate rating counts may include eligible public ratings without text. The displayed “latest ten” list requires public text.

### 5.3 Ordering and identity

Sort review texts by review date descending, then stable review ID descending. Return at most ten.

Shorten guest names to first name plus last initial. Do not expose reservation IDs, full guest identity, private comments, provider raw records, phone numbers, emails, or internal analysis.

### 5.4 Language

Preserve the original text unchanged in storage. Background-prepared translations may be displayed with a clear “مترجمة” or “Translated” label. The original remains accessible. If no approved translation exists, show the original with its language label rather than inventing or silently rewriting it.

### 5.5 Summaries

Use provider-backed category scores only when they are valid and linked to the same listing. If a category score is missing or conflicts with the current review set, omit it and flag the conflict internally.

The first implementation may show deterministic topic-mention counts from eligible public text for cleanliness, space, response/service, location, accuracy, and value. Each topic shows a numerator and denominator, such as “ذُكرت النظافة في 7 من 16 مراجعة.” These are text mentions, not category ratings, and must be labeled accordingly. No generated marketing summary is published.

### 5.6 Public contract

The listing payload adds a review object with:

- `rating_value`
- `rating_scale`
- `rating_count`
- `text_review_count`
- `source_label`
- `topic_mentions[]`
- `category_scores[]`
- `latest_reviews[]`
- `empty_state_ar`
- `empty_state_en`

The public contract must never contain `private_review`, `reservation_id`, provider raw records, or a full guest name.

## 6. Listing Operations Workspace

Use one easy page per apartment with these sections:

1. Identity and photos.
2. Space and verified amenities.
3. Location and closest approved places.
4. Arabic and English structured content.
5. Monthly price and commercial terms.
6. Review readiness.
7. Final review and approval.

The workspace must:

- Prefill safe facts from existing sources.
- Show the source and freshness for each field.
- Translate technical failure codes into clear Arabic actions.
- Save drafts without deleting source data.
- Preserve all revisions and audit changes.
- Provide “save and continue to next apartment.”
- Provide a direct internal customer-preview link.
- Filter by missing section, blocker, approval state, and freshness.

Approval cannot bypass required public checks. Internal preview remains the place to inspect incomplete homes.

## 7. Reliability and Error Behavior

### 7.1 Last-known-good snapshot

The monthly snapshot includes listings, calendars, prices, approved content, important places, commercial terms, and public review projections. A failed refresh must not replace a valid snapshot.

### 7.2 Public failure states

- Stale calendar: do not promise availability; explain that the team must confirm.
- Missing official price: do not show a fabricated estimate; remove the listing from public dated results.
- Missing exact deposit: block public publication.
- Missing reviews: show the honest listing-specific empty state.
- Broken WhatsApp configuration: show an unavailable contact state and operations blocker.
- Analytics failure: do not block browsing, matching, listing display, or lead preparation.
- Source timeout: serve the last-known-good snapshot and mark freshness internally.

### 7.3 Operations health

The monthly operations view adds review coverage and displays:

- Last successful refresh.
- Received, valid, blocked, previewed, and publicly published homes.
- Calendar, official price, Arabic/English content, review, and image coverage.
- WhatsApp and working-hours configuration.
- Title-bedroom and content conflicts.
- License expiry and other publication blockers.
- Four-to-six-month readiness.
- Red launch blockers with plain-language actions.

## 8. Analytics and Lead Outcomes

Extend the existing monthly funnel with these privacy-safe events:

- `monthly_landing_view`
- `monthly_entry_route_choice`
- `monthly_matcher_start`
- `monthly_matcher_answer`
- `monthly_price_priority_selected`
- `monthly_matcher_complete`
- `monthly_result_impression`
- `monthly_no_match`
- `monthly_listing_view`
- `monthly_review_section_view`
- `monthly_price_breakdown_open`
- `monthly_whatsapp_click`
- `monthly_lead_created`
- `monthly_team_response`
- `monthly_lead_booked`
- `monthly_lead_lost`

The lead reference connects the website session to the WhatsApp outcome. Do not store message content or unnecessary personal information.

Controlled lost reasons remain: price, unavailable dates, location, space, contract terms, no response, or booked elsewhere.

There is no invented launch conversion target. Record a 14-day baseline by entry route, purpose, price priority, and device. Then set improvement targets from Ouja’s own observed funnel. The first diagnostic comparison is listing view → price interaction → WhatsApp lead, with price-related lost outcomes separated from unavailable-date outcomes.

## 9. Visual and Interaction Rules

- Arabic-first, RTL, with a persistent English switch.
- Quiet cream, palm green, and bronze luxury palette.
- IBM Plex Sans Arabic or the existing approved Arabic font stack.
- Large real property photography and restrained shadows.
- One clear primary action per section.
- Sticky desktop price card and mobile bottom action where it does not hide content.
- Functional emojis only under the approved rule.
- Loading skeletons, honest empty states, and specific recovery actions.
- Visible focus, keyboard navigation, sufficient contrast, semantic headings, descriptive button labels, and reduced-motion support.
- No placeholder inventory, fake maps, fake rating values, fake reviews, or generic apartment photography in the delivered product.

## 10. Module Boundaries

Keep the existing monthly URLs and route adapters. Do not expand `bot.py` with new public UI logic.

Focused responsibilities:

- `monthly_public/contracts.py`: stable matcher and review payload contracts.
- `monthly_public/matching.py`: hard eligibility and approved price-priority ranking.
- `monthly_public/reviews.py`: review normalization, privacy projection, ordering, and summaries.
- `monthly_public/snapshot.py`: last-known-good public review and listing snapshot integration.
- `monthly_public/presentation.py`: bilingual public listing presentation.
- `monthly_public/analytics.py`: new funnel events and outcome dimensions.
- `monthly_public/catalog_profiles.py`: staff overlays and source-safe prefills.
- `monthly_public/static/monthly.js`: customer journey rendering and events.
- `monthly_public/static/monthly.css`: responsive visual polish and accessibility.
- Operations UI files: review coverage, conflicts, and preview links.

No customer-facing route may perform a provider network request.

## 11. Verification

### 11.1 Automated tests

Add tests for:

- Price-priority contract validation and ranking behavior.
- Hard fit and availability winning over price priority.
- No price-first revenue ranking.
- Review listing-ID isolation.
- Latest-ten ordering and fewer-than-ten behavior.
- Aggregate rating and text-count separation.
- Name shortening and private-field exclusion.
- Translation labeling and original preservation.
- Topic mention counts and category-score omission on conflict.
- Last-known-good review snapshot behavior.
- No provider calls on public customer requests.
- Internal preview including incomplete homes.
- Public publication still enforcing required data.
- Missing WhatsApp and missing exact deposit behavior.
- Analytics event contracts and no message content or PII.

### 11.2 Browser journeys

Run Arabic and English, mobile and desktop journeys for:

- Work or relocation with each price priority.
- Family stay with flexible dates.
- Treatment near an approved hospital.
- Visit near an approved venue.
- Full-catalog browsing.
- Listing review reading and expansion.
- Four-to-six-month preliminary pricing.
- Stale calendar and missing official price.
- Missing WhatsApp configuration.
- Outside-working-hours contact.
- Back navigation and changed answers.

Inspect clipping, spacing, Arabic direction, image crop quality, sticky actions, focus order, loading, errors, and long review text.

### 11.3 Content and performance checks

- Scan for discount language, crossed-out prices, placeholders, mixed-language amenities, duplicate descriptions, fake counts, and public private-review leakage.
- Confirm all public images and locations come from verified Ouja sources.
- Run accessibility and performance checks on homepage, matcher, results, browse, listing, and contact states.
- Confirm analytics failure does not block the customer journey.

## 12. Delivery and Rollback

Implement in verified milestones with small commits, then perform one final push after tests and visual review pass.

The push may trigger the existing Railway deployment flow. After push, verify the public URL and deployment health without changing production data or configuration.

Rollback is a normal revert of the upgrade commits. Existing source listing data, reviews, and staff revisions remain intact because the design does not delete or rewrite them.

## 13. Known External Blocker

The real Ouja WhatsApp number is not available in the current approved configuration. The implementation must complete and test the configuration path, keep the contact action safely blocked, and display the blocker in operations. No number will be guessed or copied from an unapproved source.

This blocker prevents calling the WhatsApp handoff production-ready, but it does not prevent implementing, testing, previewing, committing, and pushing the rest of the approved upgrade.
