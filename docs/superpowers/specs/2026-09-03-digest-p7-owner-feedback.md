# Digest P7 — the owner's first-issue feedback (2026-09-03): root causes, research, rules

Status: **built 2026-09-03 (owner «تمام»), pushed to main.** Golden regenerated with the owner's word. Verified live run: 3 events with venues named + uncropped images, 3 films with posters, club logos on the fixtures page, Bujairi as the place (King Salman Park / zoo / Boulevard excluded with reasons). Owner's words: «لا تعتذر، افهم ليه صار كذا عندك بالكود، عدله،
سو ريسيرتش، جب لي سيد ودفة عشان يفهم وش صاير بالدنيا، وحط رولز عشان ما يعود يهج».

## 1. Why each fault happened — in the code, not in luck

| What he saw | Root cause in the code | Fix |
|---|---|---|
| Event photos cropped badly (Big Sam's face cut, «REBORN» cut) | `render/html.py` puts every image in a fixed-ratio box (`aspect-ratio` 1/1 or 21/9) with `object-fit: cover`. Platinumlist's images are 1200×630; the box cropped them. | `art.py` stores the image's real width/height; the card box takes the image's own ratio; `object-fit: contain` as the last resort. **No crop, ever.** Test: the rendered `.art` box ratio equals the image ratio within 1%. |
| Subtitles «sound weird» («الخميس بالرياض، حضّر نفسك») | `build._polish` let the model REWRITE the sub freely, and the deterministic fallback («الجمعة · من ١٥٠ ريال») had no venue because it was built before the event page was opened. | Sub becomes a deterministic **facts line built after enrichment**: `<day date> · <venue> · <price>`. The model is only allowed to write the section **claim** (the page headline), under copywriting rules (specific, concrete, no adjectives, ≤ 6 words), and it is re-checked. Test: every card's sub contains a date, a place and a price/«مجاني»/«حسب العرض». |
| Films: letter tiles instead of posters, no ratings | Brief §7 forbade posters; the owner overrides that today. elcinema's film page exposes the poster at 640×960 and 1000×1500 on the **same site** as the film link, plus the IMDb id. | Posters from elcinema (same-site rule holds). Ratings via the search tool restricted to imdb.com + rottentomatoes.com, kept only when the tool actually opened the page; printed with the source in the foot. Direct fetch of IMDb is blocked (202/empty) and scraping RT's HTML is against its terms — we cite, we do not scrape. |
| Matches: type-only band, no logos | Brief §7 forbade crests; owner overrides. The FA's own schedule links each club to `team.php?id` and serves a 400×400 PNG logo from the same site. | Club logos from saff.com.sa (12 Roshn clubs mapped from the schedule page itself). Players' photos: not from any source we may use — logos only. |
| «حديقة الملك سلمان مب مفتوحة؟» | `digest/data/worth.json` was seeded by me from memory with a hedge («الأجزاء المفتوحة») and **no source**. Research: first phase opens late 2026 ([ArchDaily](https://www.archdaily.com/1038859/king-salman-park-advances-toward-2026-opening-on-former-riyadh-airbase)). A guess dressed as a fact. | The dataset below + a guard rule: **a place may appear only with `status: open`, a source URL that answers, and `verified_on` ≤ 90 days old.** «Expected», «under construction», «phase 1 soon» are never eligible. |

## 2. What the research found (2026-09-03)

| Place / thing | Status | Source |
|---|---|---|
| King Salman Park | **Not open.** Phase 1 expected late 2026, completion 2027. | [ArchDaily](https://www.archdaily.com/1038859/king-salman-park-advances-toward-2026-opening-on-former-riyadh-airbase), [ArchUp](https://archup.net/king-salman-park-riyadh-2026/) |
| Bujairi Terrace | Open. Sat–Tue 9am–12am, Wed–Fri 9am–1am. **Free access 1 May – 30 Sep 2026** (official). | [diriyah.sa](https://www.diriyah.sa/en/bujairi-terrace) |
| At-Turaif (UNESCO) | Open. Sat–Thu 10am–12am, Fri 2pm–12am, last entry 11pm. | [diriyah.sa](https://www.diriyah.sa/en/at-turaif) |
| Riyadh Zoo (الملز) | Reopened Nov 2025 for Riyadh Season, free entry, «open until 3 Jan 2026». **Status after that is unverified** → ineligible until checked. | [Arab News](https://www.arabnews.com/node/2623661/saudi-arabia) |
| Boulevard World | **Seasonal.** Closed 2 May 2026; returns with Riyadh Season 2026-27 (Oct, date TBA). | [House of Saud guide](https://houseofsaud.com/travel/riyadh-season-guide/) |
| Boulevard City | Seasonal anchor zone of Riyadh Season (Oct–May). | same |
| Riyadh Season 2026-27 | Opening date **not announced**. Known dates inside it: Six Kings Slam 21–24 Oct 2026; WWE Crown Jewel 7 Nov 2026 (Kingdom Arena). | [Asharq Al-Awsat](https://english.aawsat.com/sports/5301139-turki-alalshikh-announces-six-kings-slam-part-riyadh-season-october), [WWE](https://corporate.wwe.com/about/news/2026/09-01-2026) |
| Noor Riyadh 2026 | **Dates not announced.** 2025 edition ran 20 Nov – 6 Dec. | [RCRC](https://www.rcrc.gov.sa/en/fourth-edition-of-noor-riyadh-to-start-on-november-28/), [Wikipedia](https://en.wikipedia.org/wiki/Noor_Riyadh) |
| Sports Boulevard | Parts open: Promenade Track, Al-Rimal Sports Park, parts of Wadi Hanifah. | [Visit Saudi](https://www.visitsaudi.com/en/riyadh/stories/sports-boulevard) |
| King Abdullah Park (الملز) | **Unverified** (no reliable 2026 status found) → ineligible until checked. | — |
| National Museum, Masmak, Kingdom Centre bridge, KAFD, Wadi Hanifah | Open (long-standing), each needs a live official URL in the dataset. | to be HEAD-checked at build |

## 3. The seed + dataset «سيد ودفة» — `digest/data/riyadh.json`

One file the bot reads before it suggests anything, owner-editable (a `$STATE_DIR/digest/riyadh.json` copy wins):

```jsonc
{
  "generated": "2026-09-03",
  "calendar": [                                   // what shapes a Riyadh weekend
    {"key": "riyadh_season", "ar": "موسم الرياض", "window": ["2026-10-01", "2027-03-31"], "confirmed": false,
     "note": "opening date TBA; Six Kings Slam 21–24 Oct, WWE Crown Jewel 7 Nov", "source": "…"},
    {"key": "national_day", "ar": "اليوم الوطني", "window": ["2026-09-23", "2026-09-23"], "confirmed": true},
    {"key": "founding_day", "ar": "يوم التأسيس", "window": ["2027-02-22", "2027-02-22"], "confirmed": true},
    {"key": "noor_riyadh", "ar": "نور الرياض", "window": null, "confirmed": false, "note": "2026 dates not announced"},
    {"key": "ramadan", "ar": "رمضان", "window": ["2027-02-08", "2027-03-09"], "confirmed": false, "note": "approximate"}
  ],
  "places": [                                     // «يستاهل الزيارة» candidates
    {"slug": "bujairi", "ttl": "البجيري", "status": "open", "kind": "permanent",
     "hours": "السبت–الثلاثاء ٩ص–١٢م، الأربعاء–الجمعة ٩ص–١ص", "price": "مجاني حتى ٣٠ سبتمبر",
     "district": "الدرعية", "lat": 24.736, "lng": 46.574,
     "url": "https://www.diriyah.sa/en/bujairi-terrace", "verified_on": "2026-09-03", "verified_by": "diriyah.sa"},
    {"slug": "king-salman-park", "status": "not_open", "expected": "late 2026",
     "url": "https://www.archdaily.com/1038859/…", "verified_on": "2026-09-03"},   // kept so it is NEVER suggested by mistake
    {"slug": "boulevard-world", "status": "seasonal", "season": "riyadh_season", …},
    {"slug": "riyadh-zoo", "status": "unknown", "last_known": "open until 2026-01-03", …}
  ],
  "venues": [ … the existing venues.json rows, with coords and district … ]
}
```

## 4. The rules (code, tested) — «عشان ما يعود يهج»

1. `status == "open"` **and** `verified_on` within 90 days **and** the url answers 200 — or the place does not exist for the digest. `not_open`, `unknown`, `expected` never render.
2. `seasonal` places only inside their season window, and only when the window is `confirmed`.
3. Every card, every section: **date · place · price**, or the card is refused by the guard. Price may be «مجاني» / «من ١٥٠ ريال» / «حسب العرض».
4. Images are never cropped: the box takes the image's ratio. If the ratio is extreme (> 3:1), the card goes type-only instead of cropping.
5. Ratings only with a source the tool actually opened, shown with «IMDb» / «RT» labels and the source in the foot. No source → no rating, the card still ships.
6. The model never writes facts. It writes the page claim only, from the facts line, under copywriting rules; the guard re-checks length and the ban list.
7. Any fact the dataset marks `confirmed: false` is worded as unconfirmed («موعده ما انعلن») or omitted — never as a date.

## 5. Files

- `digest/data/riyadh.json` (new: calendar + places + venues), `digest/data/worth.json` retired into it.
- `digest/collect/worth.py` reads places with the rules; `digest/collect/elcinema.py` opens each shortlisted film's page for poster + IMDb id; `digest/collect/ratings.py` (new: search-tool citations); `digest/collect/saff.py` maps club → logo url from the schedule page.
- `digest/art.py`: stores w/h, adds `logo` kind; `render/html.py`: no-crop boxes, poster cards, ratings row, logo band; `render/reference_payload.json` + golden regenerated **with the owner's word** (the look changes on purpose).
- `digest/build.py`: facts-line subs after enrichment; model → claim only. `digest/guard.py`: rules 1–7. Tests for each rule.
