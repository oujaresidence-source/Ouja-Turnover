# oujares.com company homepage — design (approved 2026-10-12)

## Why
business.sa «إصدار توثيق التجارة الإلكترونية» checks that `https://oujares.com` is a sound,
working, non-impersonating store link. Until now `/` answered the plain text "Ouja bot is up".
This is the prerequisite for the Ministry of Tourism «منصة» travel licence.

## What
New package `site_home/` (pure static rendering, no JS, no Hostaway, no DB, no thread):

| Path | Page |
|---|---|
| `/` · `/en` | company homepage: who we are, links to /apartments /monthly /business, the official identity + licences card, contact |
| `/privacy` · `/en/privacy` | PDPL privacy policy (what we collect, why, 2-year retention, rights, deletion by email, SDAIA) |
| `/terms` · `/en/terms` | terms: browse-only site, Airbnb booking/payment, cancellation + refunds follow the Airbnb booking's policy, indicative prices, Saudi law / Riyadh courts |
| `/contact` · `/en/contact` | contact channels + `#complaints` (24/7, reply within 24 hours) |
| `/site/logo.png` · `/site/share.png` | the official mark + share card (bytes of `cp/assets/`, read once at import) |

Shared footer on every page: legal name, CR, national address, legal links, contact, and two
hidden slots — the travel licence (trade name + number + category) and the business.sa badge —
that render only once filled in.

## Single source of truth
`site_home/identity.py` → `SITE_IDENTITY`. Values match the commercial register exactly and are
locked by `tests/test_home_site.py`. The owner never edits Railway variables: the pending slots
(`travel_licence_no`, `business_sa_cert_url`, `business_sa_badge_img`) are filled in code.
`email`/`phone` empty → `OUJA_CONTACT_EMAIL` / `STAY_WHATSAPP`; still empty → hidden.

## bot.py (minimal)
- `/healthz` → `_handle_health` (the old text); `/` → the site. If the package fails to import or
  wire, `/` falls back to the health text so it never 404s. `/hook/{secret}` untouched.
- `robots.txt` allows `/`, `/en` and the legal pages; `sitemap.xml` lists them with hreflang
  alternates (always, even while `/apartments` is paused).

## Content rules
MSA only. No booking/payment on the site; no "book direct"; no unit count; no invented facts.
Social links (when set) are footer icons only — never a main call-to-action.

## Visual world
The /apartments guest-site palette (warm sand + gold), Thmanyah faces served by /monthly's
existing font stylesheet, the official Ouja mark. The identity card reads like an official
document and sits beside the intro on desktop (sticky), after it on mobile.

## Not in scope
/apartments, /monthly, /elite, /business, the dashboard, /api/*. Optional phase 2: the shared
footer on /apartments and /business — only with separate approval.
