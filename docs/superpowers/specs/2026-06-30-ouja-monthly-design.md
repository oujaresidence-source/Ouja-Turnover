# Ouja Monthly (عوجا بالشهر) — `/monthly` — design spec

**Date:** 2026-06-30 · **Status:** approved (owner), building v1
**Sibling of:** `/stay` (STAY_HTML) and `/elite` (ELITE_HTML). Same SPA architecture, reuses
`_gw_cache` listings + `_gw_overrides` — no new Hostaway sync, no new master store.

## Goal
A public lead-generation site for **monthly apartment stays** at `oujares.com/monthly`. Same
soul/vibe as `/stay` + `/elite` but a residential-calm identity. Guest picks a **move-in date +
number of months**, sees a **before/after** price (always, everywhere), and converts via a
**pre-filled WhatsApp message** to the team. It is NOT instant-book.

## Decisions (owner-approved)
1. **Price basis:** nightly × nights summed from the real Hostaway calendar = the "before".
2. **Discount:** auto + promo. **Visible default 15%** drives the shown "after" price. **Ceiling
   30%** is advertised as a teaser ("خصم يصل إلى ٣٠٪ في بعض الشهور") but never shown as the price.
   The real/maximum discount is unlocked only by contacting the team (WhatsApp). A **global promo
   switch** can lift the *visible* default for a season; promo % wins if larger than default.
3. **Period:** move-in date + number of months (1–6). Exact window → exact price.
4. **Add-ons:** preference-only toggles (private parking, private entry, …). Flipping one appends
   it to the WhatsApp message and pulls the matching **Hostaway amenity text**. No on-screen price.
5. **Apartments:** all visible `/stay` units appear by default; owner can hide per unit.
6. **WhatsApp:** own `MONTHLY_WHATSAPP` env, falls back to the shared `STAY_WHATSAPP`.
7. **Always show before/after** on featured cards, results, and the detail price panel.

## Positioning (angle C — hybrid)
Lifestyle hero + apartment cards sell *living here*; the moment dates are picked the page flips
into savings mode (before/after total, "add a month → save more, up to 30% — ask us"). A loud
campaign ribbon drops in when the global promo is on.

## Architecture
- **`MONTHLY_HTML`** = raw triple-quoted SPA string (same backslash/esprima trap as DASHBOARD_HTML
  — ZERO backslashes in JS, `String.fromCharCode(10)` for newlines, event delegation, `he()`
  escaping). `_monthly_render(route, listing, base)` injects `__MONTHLY_DATA__` + JSON-LD + SEO.
- **Routes:** `/monthly`, `/monthly/`, `/monthly/search`, `/monthly/id/{lid}`, `/monthly/img`
  (WebP proxy, reuses the elite proxy machinery), `/monthly/{slug}` (catch-all LAST).
- **Public API:** `/api/monthly/config`, `/api/monthly/featured`, `/api/monthly/search`,
  `/api/monthly/listing/{id}`, `/api/monthly/quote`. Analytics reuse `/api/stay/event`.
- **Admin API (token-gated via `_dash_auth`):** `/api/monthly/admin` GET + POST — read/write the
  config store. (Dashboard Manage **tab UI is v2**, a separate push, to avoid touching the giant
  DASHBOARD_HTML in the same deploy.)

## Pricing engine (pure, unit-tested before live)
- `_add_months(date, n)` — calendar-month add, clamps day to month length.
- `monthly_pricing(before_total, months, cfg)` → `{before, after, saved, pct, ceiling,
  per_month_before, per_month_after, promo, promo_label}`. Pure; tested with synthetic numbers.
  `pct = clamp(max(default, promo.pct if promo on), 0, ceiling)`; `after = round(before*(1-pct))`.
- `monthly_quote(listing_id, move_in, months, cfg)`: builds the window, calls
  `unit_availability_price` to sum the calendar (the "before"); if the calendar can't confirm,
  falls back to `price_base * nights` (estimated) so before/after ALWAYS render. Flags
  `available` (True/False/None) and `estimated`. Blocked nights → `available=False` + "كلّمنا
  للتوفر" note, lead still sends.

## Config store (`monthly_config.json`)
`{default_pct:0.15, ceiling_pct:0.30, promo:{on:false,pct:0.0,label_ar:"",label_en:""},
hidden:[listing_id…], addons:[{key,ar,en,match:[amenity keywords]}…]}`. Seeded: addons =
private parking, private entry. `_monthly_visible_snaps()` = `_gw_visible_snaps()` minus hidden.

## Env vars
`MONTHLY_ENABLED=1`, `MONTHLY_WHATSAPP` (→ STAY_WHATSAPP fallback), `MONTHLY_IMG_PROXY=1`,
`MONTHLY_DISCOUNT_DEFAULT=0.15`, `MONTHLY_DISCOUNT_MAX=0.30` (store overrides env once saved).

## Verification (CLAUDE.md routine)
`py_compile` (SyntaxWarning=error) · `pyflakes` · esprima-parse every `MONTHLY_HTML` <script> ·
`unittest` incl. new `tests/test_monthly_pricing.py` · offline screenshots via `_monthly_shots.py`.
Nothing auto-sends; additive and reversible.

## Out of scope (v1)
Dashboard Manage tab UI (v2), priced add-ons, Airbnb links (WhatsApp-only like elite), the
explore map.
