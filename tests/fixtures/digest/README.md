# digest fixtures — saved live pages (2026-09-02)

Fetched once with the honest identity `Mozilla/5.0 (compatible; OujaDigest/1.0; +https://oujares.com)`
and never edited. Every collector test parses these offline; `_fake_http.py` is the stand-in
for `digest/net_live.py`.

| file | source | note |
|---|---|---|
| `platinumlist-this-weekend-20260902.html` | riyadh.platinumlist.net/ar/calendar/this-weekend | day-grouped cards; 12 cards, 1 sold-out |
| `platinumlist-event-107433-20260902.html` | one event page | og:image + venue in og:description |
| `elcinema-now-sa-20260902.html` | elcinema.com/now/sa/ | 15 films, «تاريخ العرض» + genres |
| `saff-roshn-20260902.html` | saff.com.sa/championship.php?id=415 | RAW BYTES: declares utf-8, is cp1256 |
| `kooora-roshn-20260902.html` | kooora Roshn page | JSON-LD SportsEvent (UTC) — the cross-check |
| `payload_good.json` | hand-written | the schema/guard/render reference payload |

Not used, and why: `ksa.voxcinemas.com` drops non-browser connections at the Akamai edge
(HTTP/2 INTERNAL_ERROR, also on HTTP/1.1); `jdwel.com` answers with a Cloudflare challenge
page; `timeoutriyadh.com` and `jaxdistrict.com` return 403; `visitsaudi.com` and `webook.com`
are JavaScript shells with no event markup. We do not bypass bot walls or challenges.
