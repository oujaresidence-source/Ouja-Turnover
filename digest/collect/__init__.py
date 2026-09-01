# -*- coding: utf-8 -*-
"""digest.collect — one module per source. Each exposes a pure `parse(...)` that runs
on saved HTML (tests/fixtures/digest/) and a thin `fetch(week, http, now)` that pulls the
live page through the injected http adapter. Sources verified 2026-09-02:

  events   platinumlist.py  riyadh.platinumlist.net/ar/calendar/this-weekend (+ event page)
  cinema   elcinema.py      elcinema.com/now/sa/   (VOX is unreachable: Akamai drops the connection)
  fixtures saff.py          saff.com.sa/championship.php?id=415  (the FA's own Roshn schedule, KSA time)
           kooora.py        JSON-LD SportsEvent on kooora's Roshn page — the cross-check
  worth    worth.py         Ouja's curated list (digest/data/worth.json) + POI store
  any      search_secondary.py  claude_search restricted to a domain list — the fallback ladder

jdwel.com sits behind a Cloudflare challenge and is not used (we do not bypass bot walls)."""

