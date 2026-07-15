# Ouja PWA assets

This folder makes the Ouja dashboard installable to the phone home screen
(iPhone + Samsung/Android). It is **purely additive** — no existing page,
route, login, or data flow was changed.

## Files
- `manifest.webmanifest` — app identity (name "Ouja Operations", short name
  "Ouja", RTL/Arabic, brand colors). Served at **`/manifest.webmanifest`**.
- `sw.js` — service worker. Served at **`/sw.js`** (root scope). Network-first
  for live data + HTML, cache-first for static assets, with a safe update flow.
- `icons/` — every home-screen icon (192 / 256 / 384 / 512, maskable, Apple
  touch icon, favicon).
- `make_icons.py` — regenerates every icon from one source.

## Using the real logo
The icons are currently a clean gold **"ع"** placeholder on the brand tile.
To use the real Ouja logo:

1. Drop a square, transparent-background PNG here (≥ 1024×1024 is best):

   ```
   pwa/logo.png
   ```

2. Regenerate:

   ```
   python3 pwa/make_icons.py
   ```

Every icon is rebuilt from the logo automatically (centered on the brand tile
with the right safe-zone padding per platform). Commit + push → Railway
redeploys → new icon everywhere.

## Serving / hosting
PWAs require **HTTPS**. In production the app is already served over HTTPS by
Railway (`https://worker-production-*.up.railway.app`), so nothing extra is
needed. On `localhost` the browser also treats it as secure for testing.
