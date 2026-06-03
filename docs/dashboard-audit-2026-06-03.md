# Ouja Operations Dashboard Audit

Date: 2026-06-03

Scope: Arabic RTL operations dashboard in `bot.py`, based on the attached screenshots and pasted prompt. This note is the product/design handoff for the patch made in this branch.

## 1. Executive Summary

The dashboard is already useful because it collects the team's live operational surfaces in one place: guest replies, escalations, arrivals, cleaning, maintenance, pricing, listings, projects, and finance.

The main weakness is not missing decoration. It is operational confidence. Operators need to scan risk, act safely, and understand what will happen before pressing buttons. The first patch therefore hardens shared UI primitives instead of redesigning one page in isolation:

- Severity-aware badges in navigation and mobile tabs.
- Safer Arabic/English/number rendering with bidi isolation.
- Better wrapping for guest names, unit codes, money, and mixed text.
- Actionable empty states.
- Busy states for risky bulk actions.
- A confirmation summary before sending many guest replies.

## 2. What This App Should Become

The app should be a compact Arabic RTL command center for daily short-stay operations:

- Home answers: what needs attention now?
- Inbox answers: what can be replied to safely, and what needs a human?
- Calendar and pricing answer: where is occupancy or rate pressure?
- Cleaning, maintenance, and PMO answer: what blocks readiness?
- Listings, quality, finance, and reports answer: what is structurally unhealthy?

The design should feel like a control room, not a marketing dashboard. Calm surfaces, dense lists, predictable controls, clear severity, and explicit confirmations matter more than large decorative cards.

## 3. Screenshot Audit By Page

Home:
- Good: strong operational overview and daily numbers.
- Needs: above-the-fold is crowded; alerts, arrivals, and activity compete. Risk rows should sort by urgency and source.
- Patch impact: shared badge severity and mixed text handling improve scan stability.

Inbox:
- Good: useful split between automatic replies, escalations, and pending replies.
- Needs: bulk approve was too broad for a risky communication workflow. Red/yellow states were present but not consistently explained.
- Patch impact: bulk action now says review/send and shows a confirmation summary before sending.

Calendar:
- Good: revenue heatmap is valuable.
- Needs: large tables need sticky context, better legend clarity, and virtualized rendering for many units/days.
- Future: freeze unit column, show day detail drawer, and separate occupancy from price signals.

Guests:
- Good: direct guest registry exists.
- Needs: empty states should tell the operator the next action.
- Patch impact: guest empty state now carries explicit title/action data for styling and future localization.

Cleaning:
- Good: team/unit mapping is clear.
- Needs: selected units, linked channels, and schedule conflicts need stronger visual separation.
- Future: add "needs channel", "scheduled", and "blocked" filters.

Maintenance:
- Good: ticket list uses priority/status.
- Needs: high volume requires grouping by unit, source, and recurrence.
- Future: add SLA aging, repeated issue detection, and quick close with audit note.

Pricing and Strategies:
- Good: revenue opportunities and locked listings are surfaced.
- Needs: price-writing actions must always show why, before/after, source, and rollback.
- Future: add dry-run mode, price-change audit trail, and a "safe to apply" checklist.

Apartment Detail:
- Good: unit detail shows bounds and calendar.
- Needs: calendar cards should explain disabled or missing values, not just show dashes.
- Future: show last sync, data freshness, min/max origin, and override history.

Design Requests and PMO:
- Good: request/project tracking exists.
- Needs: empty states and project status language should distinguish "nothing exists" from "data failed to load".

Listings:
- Good: Hostaway sync and setup health are visible.
- Needs: setup issue chips should be categorical and sortable.

Sidebar:
- Good: complete navigation.
- Needs: count badges should communicate severity, not only volume.
- Patch impact: badge severity now derives from each page's operational meaning.

## 4. Codebase Audit

The current shape is a large monolith:

- `bot.py` contains Discord bot logic, Hostaway integration, API routes, data persistence, and the full dashboard HTML/CSS/JS string.
- `DASHBOARD_HTML` is intentionally a plain triple-quoted string. JS edits must avoid accidental Python escaping issues.
- The dashboard state is hydrated from API calls and local storage, with many shared render helpers.

Primary risks to reduce next:

- Mixed responsibilities make regressions easy.
- Critical actions need consistent audit logs, confirmations, and permission checks.
- Large lists/tables need pagination or virtualization.
- Hostaway write flows need dry-run/live separation.
- User-facing empty states should distinguish "no data", "loading", and "failed".
- Repeated UI patterns should become shared helpers instead of page-specific HTML strings.

## 5. Design System Direction

Keep the current warm neutral/gold identity, but systematize it.

Tokens:
- Background: warm off-white.
- Surface: white and soft neutral panels.
- Border: low-contrast warm gray.
- Accent: gold for primary operational actions.
- Danger: red for human attention, risk, overdue, blocked.
- Warning: amber for review needed.
- Success: green for safe/completed.
- Info: blue/neutral for passive count states.

Component primitives:
- Page header with title, subtitle, actions, freshness.
- KPI card with icon, value, label, status.
- Alert row with severity and action.
- Data table with sticky context and safe wrapping.
- Empty state with title and next action.
- Confirmation dialog for bulk or external writes.
- Busy/disabled state for async actions.

Patch additions:
- `.badge` severity classes.
- `.text-safe` and bidi-safe selectors.
- `[aria-busy="true"]` spinner state.
- 36px minimum control height for reliable click targets.

## 6. Navigation Redesign

Navigation should communicate where attention is required:

- Red badge: urgent human attention or blocked workflow.
- Amber badge: review recommended.
- Blue/neutral badge: informational count.
- Group badge: shows the strongest severity inside the group.

The patch applies this to side navigation and mobile bottom navigation. Future work should add a command/search shortcut and a "today focus" filter that jumps to the most urgent page section.

## 7. Page Enhancements

Home:
- Split "urgent now", "today", and "trend" into clearer bands.
- Add source tags for each urgent item.

Inbox:
- Require review summary before bulk sending.
- Show why a reply is automatic, pending, or escalated.
- Add confidence thresholds with visible reason text.

Calendar:
- Freeze unit names.
- Make legend persistent.
- Add row grouping by building/group.

Pricing:
- Add before/after, reason, source, and rollback for every price action.
- Separate opportunity discovery from price application.

Maintenance:
- Add SLA age and repeated issue grouping.
- Add unit-level history drawer.

Cleaning:
- Show missing Discord channel as a setup issue.
- Add day/week mode and team workload count.

Listings:
- Replace freeform "needs setup" with categorized chips.
- Add bulk setup review.

Finance:
- Treat verification actions as financial approvals with audit notes.

## 8. Button And Control Audit

Primary actions:
- Use gold only for the next intended action.
- Use explicit verbs: review, send, apply, sync, export.

Risky actions:
- Must show confirmation summary.
- Must enter busy/disabled state while running.
- Must log result and partial failures.

Filters:
- Should be segmented controls when options are mutually exclusive.
- Should preserve selected state in URL hash or local storage.

Icon buttons:
- Need `aria-label` and tooltip/title.
- Should keep stable square dimensions.

Patch additions:
- Navigation badges now have labels/titles.
- Bulk send has a confirmation summary.
- Bulk button enters `aria-busy` while sending.

## 9. Dashboard Data And API Improvements

Recommended next API contracts:

- Standard response envelope: `{ ok, data, error, meta }`.
- Standard pagination: `{ items, nextCursor, total }`.
- Standard mutation result: `{ ok, applied, skipped, failed, auditId }`.
- Standard freshness metadata: `{ source, syncedAt, staleAfter }`.

For Hostaway writes:

- Add dry-run endpoint before live apply.
- Persist before/after snapshots.
- Store who clicked, when, source page, and rollback metadata.

For inbox:

- Store reply confidence, reason, message type, reviewer, and sent result.

## 10. Architecture Refactor Plan

Phase 1 - shared safety primitives:
- Add badges, bidi-safe text, empty states, busy state, and confirmation helpers.
- This phase is implemented in the current patch.

Phase 2 - extract dashboard assets:
- Move CSS and JS out of the Python string into static files.
- Keep API routes stable.
- Add a small build/check script that extracts and validates JS.

Phase 3 - componentize render helpers:
- Create shared helpers for KPI cards, alert rows, empty states, nav items, and tables.
- Replace page-specific repeated markup.

Phase 4 - harden mutations:
- Add audit logs, dry-run modes, confirmation payloads, and permission gates.

Phase 5 - performance:
- Add pagination/virtualization for inbox, tickets, listings, and calendar.
- Add cache TTL/freshness display for Hostaway-dependent pages.

Phase 6 - full UI polish:
- Rework page hierarchy, spacing, responsive behavior, and status language once the shared system is stable.

## 11. Implemented Patch

Files changed:

- `bot.py`
- `tests/test_dashboard_ui_contract.py`
- `docs/dashboard-audit-2026-06-03.md`

Code changes:

- Added bidi isolation for Arabic/English/unit/money mixtures.
- Added safer wrapping for long names, unit codes, and message previews.
- Added severity-aware badge primitives and navigation badge mapping.
- Added actionable empty state attributes for guest/inbox states.
- Added bulk inbox approval summary before sending.
- Added busy/disabled state for the bulk approval button.
- Cleaned two pyflakes issues in existing Python code.

## 12. Patch Boundaries

This patch intentionally does not:

- Change Hostaway write behavior.
- Change Discord bot behavior.
- Split `bot.py`.
- Replace the visual identity.
- Rename pages or routes.
- Add new external dependencies.

Those are better handled after the shared safety primitives are stable.

## 13. Tests Added

`tests/test_dashboard_ui_contract.py` checks that the dashboard contract includes:

- Bidi isolation.
- Safe wrapping.
- Severity badge primitives.
- Actionable empty states.
- Busy-state support.
- Bulk approval confirmation helpers.

This is a small contract test, not a full browser visual test. It is meant to catch accidental removal of the new shared safety primitives.

## 14. QA Checklist

Before deploying a dashboard change:

- Compile `bot.py`.
- Run pyflakes.
- Extract dashboard scripts and parse them with Node.
- Open home, inbox, calendar, pricing, cleaning, maintenance, listings, and PMO.
- Test Arabic/English mixed names and unit codes.
- Test mobile width for bottom navigation.
- Test empty, loading, and failed states.
- Test every external write action with a confirmation path.

## 15. Deployment Checklist

- Confirm backup exists.
- Confirm no unrelated user files were reverted.
- Confirm Hostaway write endpoints were not changed unless intended.
- Confirm Discord tokens/secrets are not printed or moved.
- Confirm dashboard JS parses before restart.
- Restart only after checks pass.
- Watch logs after first live request.

## 16. Before And After

Before:
- Counts existed, but did not consistently communicate severity.
- Bulk inbox action was too terse for a high-risk workflow.
- Mixed Arabic/English/number text could wrap or reorder poorly.
- Empty states were often passive.

After:
- Navigation badges carry count and severity.
- Bulk inbox send requires a review summary.
- Mixed RTL/LTR values are isolated and safer to scan.
- Empty states can name the missing data and next action.
- Async bulk send has a visible busy state.
