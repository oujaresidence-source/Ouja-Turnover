# Digest P9 — the owner's seven questions on the first poster (2026-09-03), answered in code

| Question | Cause | Fix (tested) |
|---|---|---|
| Some films have no IMDb rating | Two causes: (a) the three films released THIS Thursday have no IMDb rating yet — IMDb needs votes; (b) the search tool sometimes did not open the IMDb page, and a rating without an opened page is never printed. | (a) a film released this weekend without a rating now says «جديد · التقييم ما نزل بعد» instead of showing nothing; (b) the query carries the exact IMDb id from elcinema, up to 5 lookups. |
| The QR opens an Egyptian cinema site | elcinema.com was the film source AND the QR target. | The QR now opens **muvi cinemas' Arabic movie finder** (the only Saudi chain that answers a plain request — VOX, AMC, Empire, Reel refuse). elcinema stays the info source (poster, genres, IMDb id) via `info_url`. The card line names muvi. |
| A long link for the podcast | Apple's canonical page url carries the Arabic show name percent-encoded; the link verifier stored the redirect target. | The card uses Apple's short form `podcasts.apple.com/sa/podcast/id<ID>` and the verifier keeps it (KEEP_SHORT_HOSTS). Clean QR. |
| «Old» podcasts | The Saudi chart's #1 is a years-old show; the chart says nothing about freshness. | The iTunes lookup fetches each top show's newest episode; a show with an episode in the last 7 days outranks the chart order, and the card says «حلقة جديدة: …» with the episode title. |
| «this Thursday» wording | The model's claim said «هذا الأسبوع»/«الخميس». | Prompt rule + `voice.weekend_wording`: the period is always «هالويكند»; fallbacks in the story and cinema claim changed too. |
| الاتحاد and النصر logos missing | The FA schedule's thumbnail for الاتحاد is 50×50 (below the 200 px floor) and `logos_for` returned None when EITHER side failed — so النصر vanished with it. | Logos are per side; a small thumbnail is upgraded from the club's team page (`saffteamlarge…png`); the headline band needs both sides large, the table takes any size. |
| البجيري has no picture | diriyah.sa blocks bots; the ticket page's only image is a third-party logo. | Places without a same-site image get a **free-licence Wikimedia Commons photo** (CC0 / public domain / CC BY / CC BY-SA only), chosen by a `commons_query` in riyadh.json, with the credit printed on the page and the poster. This week: At-Turaif, CC0. |

Golden regenerated (text of the cinema line and the weekend wording changed on the owner's instruction).
