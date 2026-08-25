# Monthly Priority Places and Apartment Proximity Design

## Decision

Ouja will import the approved workbook once as a versioned data migration. The dashboard will not gain a general-purpose Excel uploader. The five university rows are excluded, leaving 25 active, directly approved destinations across business, hospitals, family retail, Riyadh Season, and events.

## Outcomes

- The 25 selected destinations appear in the existing **Approved places** workspace with their verification evidence.
- Each apartment location step shows its five nearest approved destinations when the apartment pin is verified.
- The customer matcher uses the same approved destination registry and never uses a separate location list.
- No travel time is shown. Only straight-line distance calculated from two verified coordinate pairs is allowed.
- The one-time migration never overwrites a destination later edited by staff.
- The review screen explains the exact invalid field and keeps its percentage and blocker list consistent with the current form values.

## Source and Inclusion Rules

The source workbook is `Ouja_Monthly_Priority_Places_2026-08-25.xlsx`, sheet `الوجهات`, rows 6–35. Rows with `category_id=universities` are excluded. The remaining source fields are mapped as follows:

| Workbook field | Stored field |
| --- | --- |
| `place_id` | stable destination ID |
| Arabic and English names | customer and staff labels |
| category ID and bilingual category | staff grouping and health counts |
| priority | display order within a category |
| Arabic and English address and district | staff verification context |
| latitude and longitude | verified destination coordinates |
| official and coordinate source URLs | staff evidence |
| review cadence and verification date | operational review metadata |
| reason and operations note | staff-only evidence |

Purpose tags are reduced to the four approved customer purposes without inventing a new journey:

- business hubs → `work`
- hospitals → `treatment`, `family`
- family retail → `family`, `visit`
- Riyadh Season → `visit`, `family`
- events and conferences → `work`, `visit`

Unsupported secondary tags such as relocation, patient support, lifestyle, entertainment, and conference are not exposed as customer purposes.

## One-Time Migration

A focused `priority_places` module owns the immutable source rows, validation, and nearest-place calculation. A versioned migration key records successful application in the existing catalog database. On startup:

1. Validate all 25 rows before any write: unique safe IDs, bilingual names, allowed category, allowed purpose, Riyadh coordinates, HTTPS evidence URLs, and a verification date.
2. Start one database transaction.
3. For each missing ID, create revision 1 and approve it as active.
4. For an existing ID, preserve the existing record without modification and report it as skipped.
5. Record the migration key only after all rows are valid and the transaction succeeds.

Any validation or write failure rolls back the entire migration. A restart is safe: once applied, the migration returns the stored result without creating new revisions.

## Dashboard Experience

The places tab gains a concise summary showing total active destinations and counts by category. Each place row shows its category, verification date, and review cadence in addition to the existing bilingual label and purpose chips.

The apartment survey location step gains an **Nearest approved places** panel:

- exactly five results when at least five eligible destinations exist;
- ordered by straight-line kilometres, then priority, then stable ID;
- bilingual destination and category labels;
- distance rounded to one decimal kilometre;
- map and verification-source links for staff;
- an explicit empty state when the apartment coordinate is absent or unverified.

This panel is staff-facing proof. The public listing and matcher continue to show proximity only through the existing approved-place contracts.

## API and Health Contract

The listing operations response adds `nearest_places`, computed from the effective apartment profile and active approved destinations. It exposes only staff-safe location evidence, never guest guide secrets.

Catalog health adds:

- migration state and version;
- imported, skipped, and excluded counts;
- active destination count by category;
- count of apartments with verified coordinates;
- count of apartments missing verified coordinates.

## Review-Screen Defect

The screenshot shows two states mixed together: the percentage is calculated from current unsaved form values, while the blocker list comes from the last server response. The server also returns the exact failing field for `language_mismatch`, but the interface displays only the generic message. The repair will:

- compute the displayed blocker list from current form values;
- include language validity in the local readiness calculation;
- translate blocker codes instead of exposing internal English identifiers;
- display and focus the exact invalid field label returned by the API;
- retain server validation as the final authority.

## Failure and Safety Behaviour

- Invalid workbook-derived data: no destination is imported and health shows a red migration blocker.
- Existing staff record: preserved and reported as skipped.
- Missing apartment coordinates: no distance is calculated and no proximity claim is shown.
- Fewer than five active destinations: show only the verified results available.
- Snapshot refresh failure after migration: keep the previous last-known-good snapshot and report the refresh failure.
- No university data is stored or exposed by this migration.

## Verification

- Unit tests for all 25 source rows, exclusion of five universities, purpose mapping, and source validation.
- Store tests for atomic migration, restart idempotency, and preservation of existing staff records.
- Service tests for nearest-five ordering, verified-coordinate gating, and health counts.
- API contract tests for the staff-only nearest-place payload.
- JavaScript tests for the exact invalid field, live blocker calculation, translated blocker copy, and the empty location state.
- Regression tests proving no provider call occurs in the customer request path.
- Arabic and English browser inspection on desktop and mobile before deployment.

## Out of Scope

- A reusable Excel upload feature.
- Universities or a new study-purpose customer branch.
- Drive-time estimates, traffic data, or map-provider requests during customer requests.
- Automatic replacement of staff-edited place records.
