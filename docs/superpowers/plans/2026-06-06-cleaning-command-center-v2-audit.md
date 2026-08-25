# Cleaning Command Center V2 Audit

## Scope

Build one manager-friendly Cleaning Center without rebuilding the app. Reuse the current Oujact route links, cleaning reports, Google Drive photo storage, Discord review buttons, team assignment, deep-clean scheduling, and cleaning quality data.

## Current Pieces Found

- Dashboard tabs and i18n live inside `DASHBOARD_HTML` in `bot.py`. New tab ids need keys in `T.ar` and `T.en`.
- Cleaning team data already exists in `_cleaning_teams`, `_ct_team_view`, `_ct_team_lids`, and `_ct_team_name_for_lid`.
- Daily turnover/route planning already exists in `fetch_oujact_turnovers`, `_oujact_dispatch_plan`, and `_clean_ops_snapshot`.
- `_clean_ops_snapshot` already maps operational stages into `to_clean`, `in_progress`, `review`, `approved`, and `redo`.
- Route page already exists at `/oujact-route` with token-gated APIs for route data, status updates, photo upload, and report submit.
- Photo proof already exists through `_cleaning_photo_templates`, `_cleaning_reports`, `_cleaning_report_photos`, `_cleanproof_get_or_create_report`, `_api_oujact_photo_upload`, and `_api_oujact_report_submit`.
- Google Drive storage already exists through `_cleanproof_get_drive_service`, `_cleanproof_drive_folder`, and `_cleanproof_upload_drive`.
- Discord manager review already exists through `CleaningProofReviewView` and `_cleanproof_send_discord_review`.
- Dashboard manager review already exists through `openCleanProofReport` and `/api/cleaning/report-decision`.
- Deep clean remains under the existing `clean` view and `/api/cleaning/schedule`.
- Cleaning quality summary already exists through `cleaning_quality_summary` and `/api/cleaning/quality`.

## Problems Found

- Daily cleaning operations are scattered across `cleanteams`, `clean`, `quality`, apartment setup, route pages, and Discord.
- Existing `CleaningDoneView` says "Cleaning Done" and deletes the Discord turnover channel immediately, which makes cleaner completion look final before manager approval.
- The route page has a `done` action that is operationally treated as `review` in `_clean_ops_snapshot`, but the label still reads like final completion.
- Manager review exists, but it is not the obvious center of the cleaning workflow.
- Mobile managers currently inherit dashboard complexity instead of getting a dedicated phone-first command flow.
- Setup health is implicit in listings/team assignment rather than surfaced as a cleaning operations risk.

## Reuse Plan

- Use `_clean_ops_snapshot` as the source for Today pipeline jobs.
- Extend it only if needed; do not create a competing source of truth.
- Use existing report/photo APIs and `openCleanProofReport` for review details.
- Use existing route links for cleaner/team execution.
- Use existing deep clean and quality APIs inside Cleaning Center subtabs.
- Keep old tabs available as fallback while adding the new Cleaning Center.

## Move / Reframe Plan

- Add a new `clean_center` dashboard view: `مركز التنظيف / Cleaning Center`.
- Put daily manager operations in Cleaning Center subtabs:
  - Today
  - Review
  - Issues
  - Teams
  - Quality
  - Deep Clean
  - Settings
- Reframe old Discord "Cleaning Done" as "Submitted for manager review" and stop treating it as final approval.
- Reframe the route page `done` action label as submit/ready for review where safe.
- Keep Listings for setup only and show setup warnings in Cleaning Center.

## Hidden / De-emphasized Plan

- Do not remove old `cleanteams`, `clean`, or `quality` code yet.
- Do not show admin-heavy team setup on mobile manager screens.
- Do not show raw route/debug/Drive technical details in manager cards.

## Dashboard HTML Risks

- `DASHBOARD_HTML` is a normal triple-quoted string, not an f-string.
- Avoid raw JavaScript backslash escapes in string literals.
- Use existing CSS variables and warm/gold design tokens.
- Add every label key in both Arabic and English.
- Keep embedded JS parseable with esprima.
- Avoid nested card layouts and desktop tables on mobile.

## Verification Checklist

- `rm -rf __pycache__`
- `python3 -W error::SyntaxWarning -m py_compile bot.py`
- `python3 -m pyflakes bot.py`
- Check `DASHBOARD_HTML` brace, paren, and backtick balance.
- Check every nav/tab id has `T.ar` and `T.en` labels.
- Parse every embedded `<script>` block with esprima.
- Synthetic stage mapping checks:
  - no action/report -> needs cleaning
  - arrived/started -> in progress
  - submitted/pending/done -> pending review
  - manager_approved -> approved
  - manager_rejected/needs_reshoot -> needs reshoot
  - issue appears in Issues and urgent strip
  - same-day and early-departure chips surface in Today
  - manager approval requires a name/signature in dashboard

