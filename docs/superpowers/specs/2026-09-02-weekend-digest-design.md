# «وش صاير بالرياض» — the weekend digest — design spec

Date: 2026-09-02 · Package: `digest/` · Branch: `feat/weekend-digest` (worktree
`../ouja-wt-digest`, based on `origin/main` @ 0e4e64f) · Status: **P4 done — render golden locked (owner approved the look 2026-09-02), rank + art + build orchestrator; awaiting approval for P5**

This spec is the decision record. The brief (pasted as the session's first message) is
the requirement; this document says *how* it will be met inside this repo, and lists
every place where the repo's reality forced a deviation from the brief. Executors read
this together with the plan at `docs/superpowers/plans/2026-09-02-weekend-digest.md`.

---

## 0. What the owner sees

Wednesday 13:00 Riyadh. One Discord post in `#نشرة-الاسبوع`: the 1080×1920 story PNG,
then plain Najdi text listing the four sections, what was dropped and why, the sources,
and five buttons. He taps «اعتمد وانشر» and is done. «بدائل» swaps in a pre-built
candidate instantly. Nothing publishes without the tap. With `DIGEST_DRYRUN=1` (default)
the loop builds everything, writes it to disk under `$STATE_DIR/digest/<issue>/`, and
prints what it *would* post — it never touches Discord.

---

## 1. Verified repo facts (checked 2026-09-02 in the worktree on main)

| Fact | Consequence |
|---|---|
| The original checkout is on `feat/musaed-v2`, ~4k lines behind main and **missing** `cp/guard.py`, `cp/tools/build_pdf.py`, `monthly_public/fonts.py`, the Thmanyah files | All work happens in the worktree `../ouja-wt-digest` on `feat/weekend-digest` cut from `origin/main`. Never the parked checkout. |
| On main, the brief's five insertion points are exact: 298 (import), 6590 (env), 8044 (loop), 62370 (wire), 70417 (start) | Re-grep before each edit anyway. |
| `studio_digest_loop` is `@tasks.loop(time=…)` (daily). The repo's **weekly** jobs (`revenue_loop` 63660, `price_opp_loop`) are `@tasks.loop(minutes=30)` + weekday/hour check + a last-date latch | `digest_loop` follows the weekly house style, with the latch **persisted** in `digest_issues` (a redeploy re-runs a loop's first iteration — the OujaCT trap). |
| Local Python is 3.9.6; Railway is 3.13.13 (`runtime.txt`) | Package code is 3.9-compatible: no `match`, no `X \| Y` annotations, no parenthesised context managers. |
| `owner_report`'s frozen pixel test is **environment-locked** and deliberately not in CI (its README: pixel md5 differs across Chromium builds; text md5 is stable) | The digest's frozen test uses a three-part fingerprint (§8.4) so it is strict *and* portable. Pixels are still compared, with a bounded tolerance. |
| There is **no Google Places tooling** in the repo. Only Geocoding/Routes via `GOOGLE_MAPS_API_KEY`; the owner declined a Maps key for tiles | District chip comes from a local venue→district table + `match/poi.py` centroids, never from Places (§5.5). |
| `claude_search_json(system, user, max_tokens, model, max_uses, allowed_domains) -> (data\|None, [urls])` — the URLs actually opened | Secondary collectors use it and keep only facts whose URL is in that list. |
| `cp.guard.fold_digits(text)` and `visible_text(markup)` exist on main exactly as the brief says | Imported, not copied. |
| `fonts/` on main has Almarai + the **older** `ThmanyahDisplay-*` cut; the six good Thmanyah faces are in `monthly_public/static/fonts/` | Six files are copied into `fonts/` under digest-clear names (§3.2). `ThmanyahDisplay-*` untouched (cp uses them). |
| `requirements.txt` on main already has playwright, PyMuPDF, Pillow, brotli. `segno` is absent locally and in requirements | One line added: `segno~=1.6`. Separate owner approval (Railway rebuild). |
| The memo PDF (`…-جوال.pdf`) is 810×1440 pt, 30 pages, Skia/PDF m141; its fonts are embedded as Type3 outlines, so face names are not recoverable from the file | Geometry confirmed. Font fidelity is checked by eye against the memo at P3, not by name. |
| Local Chromium (Playwright) is 148.0.7778.96; esprima and segno import cleanly | The frozen golden is generated locally and stamped with the Chromium version. |

---

## 2. Architecture

```
bot.py ──wire({...})──▶ digest/host.py (HOST singleton, DI contract §2.1)
                          │
   Wednesday 13:00        ▼
   digest_loop ──▶ digest/build.py  (orchestrator; the only module that sequences I/O)
                     ├─ collect/*.fetch(week)  → Candidate[]   (network via HOST only)
                     ├─ links.verify(...)      → verified set  (HEAD via HOST.http)
                     ├─ art.resolve(item)      → owned|og|generated|none
                     ├─ rank.choose(...)       → primaries + alternates (pure)
                     ├─ voice.polish(...)      → copy (model via HOST, then denylist)
                     ├─ schema.validate(payload)                (pure)
                     ├─ guard.assert_clean(html, payload, week) (pure)
                     ├─ render/build.py       → pdf + png + json (Chromium, no network)
                     ├─ render/audit.py       → overflow/clip gate
                     └─ db: digest_issues / digest_items / digest_candidates / digest_rulings
                          │
                          ▼
   notify.py (pure text) + DigestView buttons in bot.py ──▶ Discord
   routes.py (/digest, /api/digest/*) + page.py (owner web preview)
```

**Rule of purity.** `schema`, `guard`, `voice` (denylist half), `rank`, `dates`, `notify`,
`art.generated`, `render/*` are pure: no `HOST`, no sockets, no db. `tests/test_digest_nonetwork.py`
imports them with `socket.socket` monkey-patched to raise and runs a full render.

### 2.1 `digest/host.py` — the DI contract

Same `_Host` class-attribute + `require()` + `wire(caps)` shape as `studio/host.py`, with
these attributes (bot.py fills them at the `_studio.wire` neighbourhood):

```
state_path      # _state_path(name) -> absolute path under $STATE_DIR
load_json / save_json
dash_auth       # _dash_auth(request) -> bool
req_role        # _req_role(request) -> role string
json_response   # _json(data, status=200)
web             # aiohttp web module
claude_json     # bot.claude_json(system, user, max_tokens=, model=) -> dict|None
claude_search   # bot.claude_search_json(...) -> (data|None, [urls])
http            # digest.net_live module (get_text, head, get_bytes) — see §2.2
listings        # () -> {lid:int -> name}
public_base     # () -> public base url (CALLABLE)
model_fast / model_premium
tz              # ZoneInfo("Asia/Riyadh")
now             # () -> tz-aware datetime
```

Compared with studio: no `inhouse/res_window/forward_calendar/reviews/api_get` (the digest
does not read Hostaway), plus one new cap, `http`.

### 2.2 Network adapter — `digest/net_live.py`

The brief says collectors must never call `requests` directly. They don't: they call
`HOST.require("http")`. The **only** file in the package that imports `requests` is
`net_live.py`, which bot.py wires as `"http": _digest.net_live`. It exposes:

```python
get_text(url, timeout=20)  -> (status:int, final_url:str, content_type:str, text:str)
head(url, timeout=12)      -> (status:int, final_url:str, content_type:str)   # falls back to ranged GET
get_bytes(url, timeout=25, max_bytes=6_000_000) -> (status, final_url, content_type, bytes)
```
One User-Agent string (`OujaDigest/1.0 (+https://oujares.com)`), redirects followed, 3 tries
on 429/5xx with backoff. Tests never import it; `tests/test_digest_nonetwork.py` asserts no
other module under `digest/` mentions `requests`, `urllib`, `http.client`, or `socket`.

### 2.3 Storage — `digest/db.py`

Reuses `brain.db` through `from brain import db as _bdb` exactly like `studio/db.py`
(no WAL, journal DELETE, busy_timeout, `closing(connect())`), with `_ensure()` +
`reset_init_cache()` + `q/q1/execute`. Tables:

```sql
digest_issues     (id PK, week_of TEXT UNIQUE, issue_no INT, status TEXT,   -- building|preview|approved|published|failed
                   payload TEXT, html_sha TEXT, msg_id INT, channel_id INT,
                   rebuilds INT DEFAULT 0, created_at, updated_at, published_at, error TEXT)
digest_items      (id PK, issue_id FK, section TEXT, slot INT, item TEXT(JSON), state TEXT)  -- primary|dropped
digest_candidates (id PK, issue_id FK, section TEXT, slot INT, rank INT, score REAL,
                   cand TEXT(JSON), reasons TEXT(JSON), used INT DEFAULT 0)
digest_rulings    (id PK, issue_id FK, ts, who TEXT, action TEXT,            -- approve|alt|rephrase|drop|rebuild
                   section TEXT, slot INT, detail TEXT(JSON))
```
`week_of UNIQUE` is the idempotency key: the loop's latch is "an issue row for this
Thursday already exists".

Files: `$STATE_DIR/digest/<issue_no>/{digest-<n>.pdf, digest-<n>.png, digest-<n>.json,
preview.html, art/*}`. Raw fetched HTML is cached under `$STATE_DIR/digest/raw/<sha>.html`
for 7 days (that is also where the first live run's fixtures are copied from).

---

## 3. Design system

### 3.1 Tokens — `digest/render/tokens.py`, the single colour source

```python
TOKENS = {
  "ink":"#0B1A2E","ink-2":"#122944","ink-3":"#1D3048","paper":"#F7F4EE","white":"#FFFFFF",
  "line":"#ECEAE5","mute":"#6B7280","gold":"#C6A15B","gold-2":"#D9C194","blue":"#1F4E79",
  "green":"#1F6F55","green-bg":"#E6EFEC","red":"#B23A34","red-bg":"#F9F1F0",
}
PAGE_W_PT, PAGE_H_PT = 810, 1440          # the memo's mobile page
STORY_W, STORY_H = 1080, 1920             # PNG story, deviceScaleFactor 2 → 540×960 CSS px
```
`--mute` is not in the memo's sampled palette; it is derived (ink at ~55% on paper) and
is the only added token. `tests/test_digest_render.py` asserts the rendered CSS contains
no hex colour that is not in `TOKENS`.

### 3.2 Fonts — `digest/render/fonts.py`

Copied from `monthly_public/static/fonts/` (md5-identical to the family zip) into `fonts/`:

```
fonts/ThmanyahSans-Regular.woff2        ← thmanyah-sans-regular.v20260827a.woff2
fonts/ThmanyahSans-Medium.woff2         ← thmanyah-sans-medium…
fonts/ThmanyahSans-Bold.woff2           ← thmanyah-sans-bold…
fonts/ThmanyahSerifDisplay-Bold.woff2   ← thmanyah-serif-display-bold…
fonts/ThmanyahSerifDisplay-Black.woff2  ← thmanyah-serif-display-black…
```
Five faces, not six: Sans Black is not used by the design (the memo's Sans Black appears
only in cover kickers; the digest's cover kicker is Serif Display Black). Serif Text is not
shipped: there are no long-form paragraphs in a poster. If P3 proves a face is needed it is
added then, with the test updated in the same commit.

`@font-face` uses **`file://` URLs** (the `cp/tools/build_pdf.py` idiom) so Chromium subsets
and embeds; base64 inlining (owner_report idiom) would add ~500 KB to every preview HTML.
Families: `"Thmanyah Serif Display"` (700, 900), `"Thmanyah Sans"` (400, 500, 700), fallback
`"Almarai", system-ui`. `tests/test_digest_fonts.py` re-derives each path from the declared
face and asserts `is_file()` and the `wOF2` magic, in the style of `test_monthly_fonts.py`.

### 3.3 Page grammar (from the memo, §3.3 of the brief — encoded as CSS classes)

- `.page` = 810×1440 pt, `overflow:hidden`, `direction:rtl`, logical properties only
  (`padding-inline-*`, `inset-inline-*`, `border-inline-start`); a test greps the CSS for
  `left:`/`right:`/`padding-left`/`margin-right` etc. and fails on any hit outside `dir=ltr` spans.
- `.eyebrow` 9pt Sans 500, letter-spacing .12em, 2px gold rule beneath. One per page.
- `.claim` Serif Display Black 44–56pt — the page title is a sentence.
- `.num` Serif Display Black 64pt + `.rider` small-cap Sans for units (e.g. `م` in `٩:٠٠م`).
- `.card` 1px `--line`, 3mm radius, 4.5mm pad, `--white` on `--paper`; status variants swap
  border + 6% tint only. No shadows anywhere (test: `box-shadow` absent from CSS).
- `.foot` 8pt `--mute`, present on every page: source list + «آخر تحقق» timestamp.
- Numerals: Arabic-Indic in prose (voice does the conversion), Western in `.tbl` cells with
  `font-variant-numeric: tabular-nums`.

Pages (one idea each):

| # | Page | Layout | Title pattern |
|---|---|---|---|
| 1 | Cover | navy, owned photo if available, dateLabel as the numeral | «وش صاير بالرياض · ٣–٥ سبتمبر» |
| 2 | Events | `g2` (2×2 cards, QR per card) | one sentence naming the strongest event |
| 3 | Cinema | `g3` typographic film cards | «ثلاثة أفلام تنزل هالأسبوع» |
| 4 | Fixtures | `fix` two-tone band table | «الجمعة ٩ المساء: الشباب والهلال» (the headline match) |
| 5 | يستاهل | `g1` one card, big | the place's own claim |
| 6 | Back | sources, dropped items, «ما لقينا…» honesty line, Ouja QR | «وين جبنا الكلام» |

Story PNG = pages 2–5 condensed onto one 9:16 frame (a separate `.story` template that reuses
the same card partials), rendered at 540×960 CSS px with `device_scale_factor=2`.

### 3.4 Voice — `digest/voice.py`

Two halves. **Pure half:** `BANNED` (compiled regex list from the brief §3.4 plus «لا يُفوَّت»,
«رحلة», «سحر») → `slop_hits(text) -> [str]`; `to_arabic_indic(text)` for prose;
`word_count(ar_text)`; `title_ok(t)` (≤4 words), `sub_ok(s)` (≤10 words). **Model half:**
`polish(item, kind) -> item` calls `HOST.claude_json` with a Najdi system prompt that carries
the ban list and *facts as JSON it may not alter*; the reply is re-checked by the pure half
and the original copy is kept if the model's version fails. Rephrase («غيّر الصيغة») is the
same function with a different seed line.

---

## 4. Content contract — `digest/schema.py`

The JSON in the brief §4, verbatim, validated by `validate(payload) -> [errors]` and
`assert_valid(payload)`. Caps and word limits are enforced here (and again by the guard on
the rendered HTML, so a template that injects text is caught too):

| Section | key | count | layout by count |
|---|---|---|---|
| فعاليات ومعارض | `events` | 2–4 | 2→`g2h`, 3→`g3v`, 4→`g2` |
| جديد في السينما | `cinema` | 0 or 3 | `g3`; 0 → page omitted |
| يستاهل الزيارة | `worth` | 0–1 | `g1` |
| مباريات الأسبوع | `fixtures` | 0–6 | `fix`; 0 → page omitted |

`items[].url` must be `https://`, present in `payload["verified_urls"]` (a list the build
attaches; the guard cross-checks). `confidence ≥ 0.75` for every primary. Fewer items → a
smaller grid; the renderer never emits a placeholder card (test: the string «قريباً» /
`placeholder` never appears in output).

---

## 5. Research layer — `digest/collect/`

Each collector: `fetch(week: Week) -> list[Candidate]`, where `Week` (from `digest/dates.py`)
is `(thu: date, fri: date, sat: date, label_ar: str, iso: str)` and `Candidate` is a dict with
`section, ttl, sub, chip, url, day, source{name,url,fetched_at}, raw_confidence, tags{category,
district}, art_hint{og_url}`.

### 5.1 Sources — as VERIFIED live on 2026-09-02 (P2)

| Module | Source | Status | Notes |
|---|---|---|---|
| `platinumlist.py` | `riyadh.platinumlist.net/ar/calendar/this-weekend` + one event page per shortlisted card | **works** | day-grouped cards; venue + og:image from the event page; sold-out cards dropped with a reason |
| `elcinema.py` | `elcinema.com/now/sa/` | **works** | replaces VOX (Akamai drops non-browser connections); «تاريخ العرض» inside [Thu−6d, Sat] = new this week |
| `saff.py` | `saff.com.sa/championship.php?id=415` (the FA's own Roshn schedule) | **works** | replaces jdwel (Cloudflare challenge — not bypassed); cp1256 despite a utf-8 header |
| `kooora.py` | JSON-LD `SportsEvent` on kooora's Roshn page | **works** | the cross-check; disagreement drops the fixture |
| `worth.py` | `digest/data/worth.json` (12 seeded places, 5 with HEAD-verified urls) | works | url-less entries resolved through the search tool or stay ineligible |
| `search_secondary.py` | `HOST.claude_search` with `allowed_domains` | works (faked in tests) | keeps an item only if its url is in the tool's opened-pages list |

**Identity.** `net_live` sends `Mozilla/5.0 (compatible; OujaDigest/1.0; +https://oujares.com)`:
browser-compatible, names us, links to us. A bare `OujaDigest/1.0` was bounced by
Platinumlist's Queue-it safety net; a spoofed Chrome string was not used. Sites that
present a challenge page (jdwel, timeoutriyadh, jaxdistrict) are simply not sources.

**Risk stated up front:** any of these sites may serve a JS-only shell or block a non-browser
UA. That is discovered at P2's live smoke, not guessed now. The fallback ladder per slot is
primary HTML → `claude_search` on the same domain → the secondary domains → drop and report.
The digest ships with fewer items rather than a guess.

### 5.2 Link rule — `digest/links.py`

`verify(urls) -> {url: final_url}` using `HOST.http.head` (ranged GET fallback), keeping only
`200` + `text/html`; same-origin redirects are followed and the **final** URL is stored. Called
twice: after collection (into `verified_urls`) and again inside `build.py` immediately before
render; a failure at render time drops the item, reflows the grid and adds a `dropped` entry.
A URL may only enter a candidate from a fetched page or from `claude_search`'s returned URL
list — `links.provenance_ok(url, seen_urls)` is asserted in the collector tests.

### 5.3 Dates — `digest/dates.py`

`week_for(now: datetime) -> Week`: the next Thu–Sat strictly after today unless today is
Wednesday or earlier in the same week, in which case this week's. Concretely: `days_ahead =
(3 - now.weekday()) % 7`; if today is Thu/Fri/Sat, the *current* weekend is already in
progress, so the digest built on a Thursday covers **that** Thursday (the brief: "including when
today is Thursday"). Frozen-clock tests for all seven weekdays, in `Asia/Riyadh`.

`label_ar(week)` → «٣–٥ سبتمبر» (same month) or «٣٠ أكتوبر – ١ نوفمبر» (crossing).

### 5.4 Confidence — in `rank.py` but computed at collection

`confidence = 0.55*tier + 0.30*agreement + 0.15*freshness`, tier ∈ {primary 1.0, secondary
0.7, search-only 0.5}, agreement = 1.0 if a second source confirms date+venue else 0.5,
freshness = 1.0 if fetched today, decaying to 0 at 7 days. Below 0.75 → alternates only.

### 5.5 District chip — `digest/places.py` (deviation from the brief)

The brief says "Google Places via the existing places tooling". There is none, and the owner
has already declined a Maps key for tiles. So: `district_for(venue_text, address_text) -> str`
matches against a curated venue→district table (`digest/data/venues.json`: Boulevard→حطين,
Boulevard World→حطين, KAFD→العقيق, Diriyah/Bujairi→الدرعية, Riyadh Front→الرياض فرونت, JAX→الدرعية,
Expo/Malham, King Fahd Stadium→الروضة… ~40 rows) and then against the district names in
`match/poi.py: NEIGHBOURHOOD_CENTROIDS`. No match → «الرياض». Proximity (§10) uses the same
table's coordinates (POIS + centroids) against the six compounds' coordinates.

---

## 6. Guard — `digest/guard.py`

`assert_clean(html, payload, week)` raises `DigestError(AssertionError)` on, each tested
individually:

1. any item whose `source` is empty or whose `fetched_at` is older than 7 days;
2. any date token in visible text outside the Thu–Sat window (Arabic month names and
   Arabic-Indic digits are folded via `cp.guard.fold_digits` first);
3. a Western digit inside a prose element (`.claim, .sub, .foot, p`) — table cells are exempt;
4. a title > 4 words or a sub > 10 words (in the *rendered* text, not just the payload);
5. a `voice.BANNED` hit anywhere in visible text;
6. a `url` in the HTML (`href`, QR payload) not in `payload["verified_urls"]`;
7. a section over its cap;
8. the word «placeholder» or an empty card.

`visible_text` and `fold_digits` are imported from `cp.guard`. A good payload passes with an
empty list. The guard runs *before* Chromium is launched — a failed guard costs nothing.

---

## 7. Artwork — `digest/art.py`

`resolve(item, issue, slot) -> {"kind": owned|og|generated|none, "src": data-uri|path, "sha256"}`,
tried in order:

- **owned** — `digest/data/owned.json` maps a slug (a compound, a POI we photographed) to an
  image URL on `public_base`; fetched through `HOST.http.get_bytes`, Pillow `thumbnail((760,760),
  LANCZOS)`, JPEG q78, base64 — the `unit_tiles()` steps, verbatim.
- **og** — `<meta property="og:image">` from the item's verified page, **same site only** (same registrable domain: Platinumlist serves its own images from cdn.platinumlist.net — same publisher, which is what makes the claim defensible),
  `Content-Type: image/*`, long edge ≥ 800 px, ≤ 6 MB, fetched within 10 s. Stored with sha256.
- **generated** — `art_generated.svg(seed, glyph, kind)` pure: navy field, gold rule, the
  glyph (a film's first letter, «ض» vs «م» halves for a fixture band) in Serif Display Black,
  and a low-amplitude line texture from an LCG seeded by `sha256(issue + slot)`. Cinema and
  fixtures always use this kind (no posters, no crests — enforced by `tests/test_digest_art.py`
  asserting `og` is never attempted for those sections).
- **none** — type-only card.

QR: `segno.make(url, error="m")` → SVG string, navy modules on cream, quiet zone 4, rendered
at ≥ 22 mm on the PDF page (the CSS sets `.qr{width:24mm}`; the audit measures it).

---

## 8. Rendering — `digest/render/`

- `tokens.py`, `fonts.py`, `html.py` (`build_pages(payload) -> str`, `build_story(payload) ->
  str`; pure; escapes with `html.escape`; zero backslashes in any embedded string),
  `build.py` (`render(payload, out_dir) -> {pdf, png, json, html}`), `audit.py`.
- Chromium: one cold `chromium.launch(args=["--disable-dev-shm-usage"])` per build, in a
  1-worker `ThreadPoolExecutor` (Playwright's sync API is greenlet-bound — the owner_report
  lesson). `page.pdf(width="810pt", height="1440pt", print_background=True, margin=0,
  prefer_css_page_size=True)`; the story via `page.screenshot(full_page=False)` on a
  540×960 viewport with `device_scale_factor=2` → 1080×1920.
- `audit.py` ports `owner_report/renderer/audit_layout.py`'s two JS checks (overflow past
  `.foot`, clipped `svg text`) and adds: every `.qr` ≥ 22 mm, every `.card` has non-empty
  `.ttl`, no element wider than the page. Runs on **every** build; a violation raises and the
  Discord message says so instead of posting a broken poster.

### 8.4 The frozen test — `digest/render/test_render_frozen.py` + `golden_fingerprint.json`

Deviation from a naive port, for a stated reason: owner_report's pixel-md5 golden is
environment-locked and therefore *not* wired into its CI. The digest's fingerprint has three
parts per page, all from the same fixed reference payload (`digest/render/reference_payload.py`):

1. `text_md5` — `md5(page.get_text())` via PyMuPDF (stable across Chromium builds);
2. `layout_md5` — md5 of the sorted list of `(class, round(x), round(y), round(w), round(h))`
   for every `.page > *`, `.card`, `.claim`, `.qr` as measured in the browser (`getBoundingClientRect`,
   rounded to whole CSS px) — this locks the *design*;
3. `pixel_md5` — `md5(pixmap(dpi=72).tobytes("png"))`, **plus** the mean absolute pixel delta
   against the golden PNG checked into `digest/render/golden/`.

Pass rule: 1 and 2 must match exactly; 3 must match exactly **or** the mean delta must be
≤ 3/255 with the golden's Chromium major version recorded in the JSON (sub-pixel AA drift
only). Anything else fails with «the look changed — revert, don't regenerate». The golden is
generated once, locally, at P3 after the owner has seen the PDF beside the memo, and is never
regenerated to make a test pass. The test is a plain `main() -> int` like owner_report's and
is *also* wrapped by `tests/test_digest_frozen.py`, which skips only when Chromium cannot
launch (so CI on a machine without Playwright stays green, and the local routine runs it).

---

## 9. Approval loop

### 9.1 Timing — `digest_loop` in bot.py

```python
@tasks.loop(minutes=30)
async def digest_loop():
    if not (DIGEST_ENABLED and _HAS_DIGEST): return
    now = now_riyadh()
    if now.weekday() != DIGEST_DAY or now.hour != DIGEST_HOUR: return
    if await asyncio.to_thread(_digest.build.already_built, now): return   # persisted latch
    ...
```
`already_built(now)` = an issue row exists for `dates.week_for(now).iso`. The pure decision
`digest.schedule.should_fire(now, day, hour, existing_week_of) -> bool` lives in the package
and is tested for every weekday and hour **before** the loop is written. Env: `DIGEST_ENABLED=1`,
`DIGEST_DRYRUN=1`, `DIGEST_CHANNEL=نشرة-الاسبوع`, `DIGEST_DAY=2`, `DIGEST_HOUR=13`.

### 9.2 Discord message

Story PNG as `discord.File` (bytes from disk), then `notify.build_message(payload, issue)` (pure:
sections as lines, dropped + reasons, sources compact, `nl = chr(10)`), then `DigestView`.

Buttons (persistent, `timeout=None`, static `custom_id`s `ouja_dg_approve / ouja_dg_alt /
ouja_dg_rephrase / ouja_dg_drop / ouja_dg_rebuild`, registered with `bot.add_view` in
`on_ready`; the message id is the key — `db.issue_by_msg(message.id)`, the decor "the thread IS
the id" idea):

| Button | State transition (`digest/approval.py`, pure + db) |
|---|---|
| ✅ اعتمد وانشر | `preview → approved`; render finals; write `$STATE_DIR/digest/<n>/`; edit the message to «تم النشر»; `published` |
| 🔁 بدائل | ephemeral view: a `Select` per section (options = candidates 2..4 with score reasons); pick → swap item, re-render preview, edit message + replace PNG |
| ✍️ غيّر الصيغة | `voice.polish(..., seed=rulings_count)` on every item, re-render |
| 🗑️ احذف العنصر | ephemeral `Select` of slots; drop → `dropped` with reason «حذفه فيصل»; reflow |
| 🔄 ابنِ من جديد | `rebuilds < 3` else refuse with reason; full re-collect |

Every press → `digest_rulings` (who, when, action, section, slot, detail). Presses require the
admin role or `manage_guild` (`_digest_may_press`, copied from `_decor_may_press` but failing
**closed**). With `DIGEST_DRYRUN=1` nothing is sent and no view exists; the build still completes
and writes files, and `tests/test_digest_approval.py` proves `notify`/`approval` produce the
same transitions with a fake sender that records calls and never opens a socket.

### 9.3 Web — `routes.py` + `page.py`

`GET /digest` (login) → the owner preview page (latest issue, its PNG, the same five actions
as HTML buttons calling `/api/digest/act`); `GET /api/digest/status`, `GET /api/digest/issue/{n}`,
`POST /api/digest/act` (`{issue, action, section, slot}`), `POST /api/digest/build` (manual
trigger, dryrun-aware), `GET /digest/<n>/{pdf|png|json}` (login). All behind `_safe` (login)
plus `_ROLE_WRITE_RULES`/`_ROLE_READ_RULES` entries `("/api/digest/", "digest")`; the tab appears
for non-admins only after the owner ticks it in الصلاحيات (existing whitelist model).
`page.py`: zero backslashes, event delegation, esprima-parsed in `tests/test_digest_page.py`.

---

## 10. Ranking — `digest/rank.py`

Pure. `score(cand, ctx) -> (total, parts)` with the brief's weights:

```
0.30 decision_value  — category prior (exhibition .9, museum .85, season .8, family .75,
                        concert .7, market .6, b2b .1) × day fit (Thu/Fri evening 1.0, Sat .8)
0.20 source_confidence — §5.4
0.15 proximity       — 1 − min(1, km_to_nearest_compound / 25) using places.py coords
0.15 audience_fit    — tags ∩ {family, couples, young} prior
0.10 novelty         — 0 if shipped in the last 6 issues (by url or folded title), else 1
0.10 owner_history   — from digest_rulings: −0.5 per past drop of the same district/source/category (floor −1), +0.25 per approve
```
`choose(cands, ctx, per_section_cap) -> {"primary": [...], "alternates": {slot: [...]}}` applies
**spread**: no two event primaries share `tags.district` or `tags.category`; greedy with a
`SPREAD_WEIGHT` bonus like `studio/plan.py`. The test feeds three Boulevard concerts scoring
higher than one exhibition + one market and asserts the mixed set wins. Alternates are the
next three by score for each slot, kept in `digest_candidates` so «بدائل» is instant.

---

## 11. Files

```
digest/__init__.py  host.py  db.py  net_live.py  dates.py  schema.py  guard.py  voice.py
digest/places.py  links.py  art.py  art_generated.py  rank.py  schedule.py  approval.py
digest/build.py  notify.py  routes.py  page.py
digest/collect/__init__.py  platinumlist.py  vox.py  jdwel.py  worth.py  search_secondary.py
digest/render/__init__.py  tokens.py  fonts.py  html.py  build.py  audit.py
digest/render/reference_payload.py  test_render_frozen.py  golden_fingerprint.json  golden/*.png
digest/data/venues.json  worth.json  owned.json
fonts/ThmanyahSans-{Regular,Medium,Bold}.woff2  fonts/ThmanyahSerifDisplay-{Bold,Black}.woff2
tests/test_digest_*.py (13 files)  tests/fixtures/digest/*.html (from the first live run)
requirements.txt (+ segno~=1.6)   CLAUDE.md (+ skills section, + a digest traps block)
bot.py: five additive insertions (§1) + DigestView + _ROLE_* entries
```

## 12. Approval stops

P0 (this document + the plan) → P1 schema/guard/voice/dates/schedule → P2 collectors on
fixtures → P3 render + fonts + frozen + audit (**owner sees a PDF beside the memo**) → P4 rank
+ alternates + art → P5 routes/page/notify/db/approval + the bot.py loop and view (DRYRUN=1) →
P6 one live dry-run week, impeccable pass, `segno` requirement + DRYRUN flip as their own
approvals.

## 13. Owner rulings (2026-09-02)

1. Cover: **type only** — no photo. 2. «يستاهل» seed list: **I seed it** (~12 places).
3. Channel `#نشرة-الاسبوع`: **create it**. 4. `segno` in requirements: **owner's call = mine** → add at P5.

Original questions kept for the record:

1. **Cover photo.** The memo's cover is a KAFD photo. The digest cover would use an Ouja
   compound photo from the public site (owned). Fine, or type-only cover?
2. **«يستاهل» seed list.** I will seed `worth.json` with ~12 places (parks, museums, trails,
   the compounds' own neighbourhoods). Does Faisal want to hand me the list instead?
3. **Channel name** `#نشرة-الاسبوع` — create it, or reuse an existing one?
4. **`segno`** goes into `requirements.txt` → Railway rebuild. Approve separately at P5.
