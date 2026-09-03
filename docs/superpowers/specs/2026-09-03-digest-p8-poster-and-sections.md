# Digest P8 — «انسخ، الصق، طوّر»: the one-poster format + new sections (owner, 2026-09-03)

Status: **built 2026-09-03 (owner «تمام»), pushed to main.** Golden regenerated (8 pages) with the owner's word. Live dry run: poster 1080×~4200 with real images, posters, logos, podcast (Apple SA chart #1), verse 94:5-6 from the API, saying. Reference: nine issues of the Ministry of Industry's
weekly «ما وراء الخميس» (WhatsApp zip, 2026-08-29). Owner asks: copy the thinking, not the
look — podcast of the week, saying / Quran verse of the week, IMDb used properly, ticket
prices «starting from», dates on every card, and more sections that support the idea.

## 1. Faults in the current build, with the cause in the code

| Owner saw | Root cause | Fix |
|---|---|---|
| «حسب التذكرة» instead of «من ١٣٩ ريال» | Platinumlist prices in the **visitor's** currency. The Railway server is in US West → the page said `54.64 USD`; `_price_ar` only understood `SAR/ر.س/ريال` → fallback text. (Locally I saw riyals, so it passed.) | `net_live` uses a fresh session with the site's own `user_currency=SAR` cookie for Platinumlist (verified: it pins riyals). Parser also reads USD/AED/EUR and converts at the site's rate only as a last resort, marked «≈». Test with a USD fixture. |
| «put the dates on every card» | Done in P7 (top screenshot shows «الجمعة ٤ سبتمبر · مركز سرد الثقافي»); the bottom screenshot is the pre-P7 issue. | Unchanged; the guard refuses a card without the day and date. |
| IMDb barely visible / missing | Ratings only render when the search tool opened the IMDb page; the row was small grey text. | A proper IMDb badge (yellow lozenge, black «IMDb», the rating in Serif Display) on every film card, **and** the search prompt now carries the exact IMDb id from elcinema so the tool opens the right page; up to 5 lookups. RT stays as a second, smaller badge. No source → the badge is not drawn. |

## 2. What the reference does that we adopt («انسخ»)

1. **One tall poster**, phone-width, everything on one scroll: header (brand, date pill, icon row), photo cards with a **district pill** top-corner and a **QR** bottom-corner, caption under the photo, a **podcast** card, a **places** block, the **fixtures** block with logos, an **occasion** header when there is one (their «يوم التأسيس» issue), a **Quran verse** strip at the very bottom, footer with the site.
2. Cards are photo-first; text is one caption line. Category icons at the top tell you what is inside before you scroll.

## 3. What we keep ours («طوّر»)

- Our tokens: cream paper, navy ink, gold rule, Thmanyah faces — not their pastel gradient.
- Facts line on every card (day+date · place · price) — the reference has only a caption; we keep the discipline.
- Sources and «آخر تحقق» in the footer; every QR from a verified url.

## 4. New outputs and sections

| Output | Size | Use |
|---|---|---|
| `digest-<n>.poster.png` (**new**) | 1080 × variable (≈ 1080×3200), 2× | WhatsApp broadcast / Discord post image — the reference format |
| `digest-<n>.pdf` (6–8 pages) | 810×1440 pt | unchanged, gains the new pages |
| `digest-<n>.png` story | 1080×1920 | unchanged |

New sections (each optional; a section without a verified source is simply absent):

| Section | Source (verified) | Card |
|---|---|---|
| **بودكاست الأسبوع** | Apple Podcasts Saudi top chart, Apple's official marketing feed (`rss.marketingtools.apple.com/api/v2/sa/podcasts/top/10`) → name, artist, page url, artwork | artwork · title · «بودكاست · <artist> · مجاني» · QR to the Apple page. Novelty: never the same show twice in 6 issues. |
| **آية الأسبوع** | Quran text fetched from `api.alquran.cloud` (Uthmani), never typed by us; the verse key chosen from a curated list of ~40 short, widely-known verses in the dataset; sequence by issue number | the verse in Serif Display, «سورة X · آية N» beneath, no image |
| **حكمة الأسبوع** | curated dataset `digest/data/sayings.json` (Arabic proverbs and attributed quotes, owner-editable) | one line + attribution; rotates by issue number |
| **مناسبة** header | `riyadh.json` calendar, `confirmed: true` only, within 14 days (National Day 23 Sep, Founding Day 22 Feb) | a strip under the header, like the reference's «يوم التأسيس» issue |

Schema: `podcast` (0–1), `verse` (0–1), `saying` (0–1), `occasion` (0–1). Guard: the verse must carry its API url + key; the podcast url must be in the verified set; the saying must exist in the dataset (no model-written sayings, ever).

## 5. Rules added
8. A price is printed in riyals from the site's own SAR view; a converted price is marked «≈» and only when SAR was unavailable.
9. Quran text comes only from the API, exact, with surah and ayah printed; if the API is down the section is absent.
10. Sayings come only from the owner-editable list; the model never writes one.
11. A rating badge is drawn only with an opened source; the IMDb id in the query must match the opened page.

## 6. Files
`digest/net_live.py` (SAR session), `collect/platinumlist.py` (multi-currency parse), `collect/podcast.py`, `collect/verse.py`, `data/sayings.json`, `data/riyadh.json` (+verses list, +occasions), `schema.py`, `guard.py`, `build.py`, `render/html.py` (+ IMDb badge, podcast/verse/saying/occasion pages), `render/poster.py` (**new**, the tall poster), `render/build.py` (third screenshot), `reference_payload.json` + golden (regenerated with the owner's word), `notify.py` (new lines), tests for each.
