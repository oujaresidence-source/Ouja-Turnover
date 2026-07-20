# Cleaning Dispatch → WhatsApp (الإرسال) — Design

**Date:** 2026-07-21
**Status:** Approved for planning (pending owner review of this spec)
**Author:** Faisal + Claude

## 1. Problem / motivation

Every day the bot already opens Discord "OujaCT" channels (at 00:05 Riyadh, refreshed
through the day) for each apartment that has a checkout, stamped with the responsible
**ops employee's** color/emoji (Nasser 🟢, Maather 🟠, Norooh 🟣, Mohammed 🔵, Ohoud 🟡).
That serves the **ops team**, who live in Discord.

But the people who actually clean — the **cleaning crews** — are on **WhatsApp**, not
Discord. Today someone has to manually translate "these apartments need cleaning" into
WhatsApp messages to the right crew. That's slow and error-prone, and it's the one place an
apartment can silently fall through.

**Goal:** every day, auto-prepare a clean, ready-to-send WhatsApp message **per cleaning
crew** listing that crew's apartments to clean, with the facts they need — and let the
dispatcher send it with one tap. Nothing gets missed.

## 2. What we are building (in one line)

A new Discord channel **`dispatch`** where the bot posts **one message per cleaning crew**,
each with a **"أرسل عبر واتساب / Send on WhatsApp"** button that opens WhatsApp with the
message already written. The dispatcher picks the crew's contact and sends.

## 3. Decisions locked with the owner

| # | Decision | Choice |
|---|----------|--------|
| Delivery | Auto-send vs. tap-to-send | **Tap-to-send only.** No WhatsApp Business API, no auto-send (burned us once — see `musaed-autosend-spam-incident`). |
| Surface | Where it lives | **Discord channel `dispatch`.** One message per crew with a link button. |
| Grouping | Per what | **Per cleaning crew** (`cleaning_team`), NOT per apartment and NOT per ops employee. |
| Auto timing | When | **Daily 21:00 (9 PM) Riyadh → posts TOMORROW's cleaning list** (crews get next-day heads-up the night before). |
| Manual command | Behavior | **`!ouja dispatch`** → smart day: **before 12:00 noon = today**, **after noon = tomorrow**. Optional `!ouja dispatch today\|tomorrow\|YYYY-MM-DD` override. Header always states the exact date. |
| Ops name in crew message | Show/hide | **Hidden in the WhatsApp text** (crews don't need internal names). **Shown on the Discord card** the dispatcher sees (ops name + emoji per apartment). |
| Crew phone | Required? | **Optional.** If a crew's number is saved → button jumps straight to that chat. If not → dispatcher picks the contact. Zero setup to start. |

## 4. Architecture

Purely **additive**. Does not touch the midnight OujaCT channel builder, the cleaner route
page, or the `schedule/` roster. Reuses existing data:

- **Which apartments need cleaning:** `fetch_oujact_turnovers()` (bot.py:995) already returns
  today's + tomorrow's turnovers, each item carrying `lid`, `listing`, `checkout`,
  `checkout_date`, `checkin_today`, `checkin_dt`, `early_departure`. We **filter by
  `checkout_date`** for the target day — no new Hostaway calls.
- **Crew grouping:** each listing record's `cleaning_team` field + `_ct_team_lids(team_id)`
  (bot.py:716). Teams: `_cleaning_teams` (bot.py:673), each `{id, name, token, created_at}`.
- **Ops owner per apartment (Discord card only):** `schedule/coverage.py` →
  `cover_for_listing_id(lid, date_iso)` / `cover_for_listing(name, date_iso)` → `{name, emoji}`,
  date-aware (covers off-day reassignment correctly).
- **Absolute links:** `PUBLIC_BASE_URL` env (already used at bot.py:2397).
- **WhatsApp link:** reuse `_wa_from_phone()` (bot.py:2768) pattern.

### 4.1 New components (all in `bot.py`, near the OujaCT block)

1. **`_dispatch_resolve_date(mode=None)`** — returns the target `date_iso`.
   - `mode` in `{None, "today", "tomorrow", "YYYY-MM-DD"}`.
   - `None` (the default for the command): `today` if `now < 12:00`, else `tomorrow`.
   - Auto loop passes `"tomorrow"` explicitly.

2. **`_dispatch_jobs(date_iso)`** — the data assembler. Returns:
   ```
   {
     "date": date_iso,
     "teams":     [ {"team": <team dict>, "items": [<turnover>, ...]}, ... ],   # only crews with items
     "unassigned": [<turnover>, ...],   # need cleaning but cleaning_team == "" → SAFETY NET
   }
   ```
   Built by filtering `fetch_oujact_turnovers()` to `it["checkout_date"] == date_iso`, then
   grouping each item by `store[str(lid)].get("cleaning_team")`. Items keep the existing
   `_oujact_sort_key` order (early departures → same-day check-ins → checkout time).

3. **`_dispatch_wa_text(team_name, date_iso, items)`** — the **crew-facing WhatsApp text**
   (clean, Arabic, no internal ops names). Format:
   ```
   تنظيف — فريق {team_name}
   {arabic weekday} {d/m} · عدد الشقق: {n}

   1. {listing} — خروج {HH:MM}{، دخول اليوم {HH:MM} (عاجل)}{ · الضيف طلع بدري}
   2. ...

   الرجاء تأكيد الاستلام
   ```
   - `دخول اليوم … (عاجل)` only when `checkin_today`.
   - `الضيف طلع بدري` only when `early_departure`.
   - `لا يوجد دخول اليوم` when no same-day check-in (optional, keep terse).
   - **Newlines built with `String.fromCharCode`-equivalent** is N/A here (this is Python, not
     the embedded JS string) — real `\n` is fine in bot.py Python code.

4. **`_dispatch_wa_url(team, date_iso)`** — builds the WhatsApp deep link, URL-encoding the text:
   - phone saved → `https://wa.me/{digits}?text={enc}`
   - no phone → `https://api.whatsapp.com/send?text={enc}` (opens WhatsApp, dispatcher picks contact)

5. **`_dispatch_embed(job)`** — the **Discord card** (what the dispatcher sees before sending).
   Same apartment list **plus** the ops owner name+emoji per line (from coverage). Title:
   `تنظيف — فريق {name} · {n} شقة · {date}`.

6. **`GET /d/{token}`** (query `?date=YYYY-MM-DD`) — `_handle_dispatch_redirect`. Resolves the
   crew via `_ct_team_by_token(token)` (bot.py:726), rebuilds `_dispatch_wa_text` **fresh** for
   that team+date, and **302-redirects** to `_dispatch_wa_url`. This keeps the Discord link
   button short (well under Discord's 512-char URL limit) and always reflects the latest data.
   **Robots-disallowed** (add to the existing disallow list). The redirect target is always a
   WhatsApp domain we construct — not user input — so it's not an open redirect.

7. **`post_dispatch(date_iso, channel=None)`** — posts to the `dispatch` channel:
   - For each team in `job["teams"]`: send `_dispatch_embed` + a **Link button**
     (`discord.ui.Button(style=link, url=PUBLIC_BASE_URL + "/d/{token}?date={date}", label="أرسل عبر واتساب")`).
   - `job["unassigned"]` non-empty → one **⚠️ «شقق تحتاج تنظيف — غير معيّنة لأي فريق»** message
     listing them (no button; prompts the owner to assign a crew). This is the miss-proofing.
   - Everything empty → single **«لا يوجد تنظيف اليوم 🎉»** note.
   - `DISPATCH_DRYRUN=1` → log the messages instead of posting (safe testing).

8. **`dispatch_daily_loop`** — `@tasks.loop(time=dt_time(hour=DISPATCH_HOUR, minute=0, tzinfo=TZ))`,
   started in `start_web_server`/on-ready alongside the other loops. Each night calls
   `post_dispatch(_dispatch_resolve_date("tomorrow"))`. Guard with `DISPATCH_ENABLED`. Include a
   once-per-day idempotency guard (like `_oujact_opened`) so a redeploy at ~21:00 doesn't double-post.

9. **`!ouja dispatch [arg]`** command — parses `arg` → `_dispatch_resolve_date(arg or None)` →
   `post_dispatch(date_iso)`; replies with which date it posted for.

### 4.2 Crew phone (optional field)

- Add optional `phone` to `_cleaning_teams[*]` records (normalized via existing phone helper).
- Surface a **phone input** in the existing cleaning-teams manage UI (the tab that calls
  `/api/cleaning/teams`, handler `_api_cleaning_teams` bot.py:43748) and persist it in the
  POST branch. `_ct_team_view` gains `phone`.
- No phone = fully functional (contact-picker path). Purely an enhancement.

## 5. Data flow

```
21:00 nightly  ──▶ dispatch_daily_loop ──▶ post_dispatch(tomorrow)
!ouja dispatch ──▶ resolve date ─────────▶ post_dispatch(date)
                                             │
                     fetch_oujact_turnovers()│  (today+tomorrow, cached window)
                       filter checkout_date  │
                       group by cleaning_team│
                                             ▼
                        per crew: Discord embed + Link button
                              button ─▶ GET /d/{token}?date=… ─▶ 302 ─▶ WhatsApp (prefilled)
                        unassigned crew-less apartments ─▶ ⚠️ safety-net message
```

## 6. Config / env vars

| Var | Default | Meaning |
|-----|---------|---------|
| `DISPATCH_ENABLED` | `1` | Master on/off for the auto loop. |
| `DISPATCH_CHANNEL` | `dispatch` | Discord channel name to post into (created if missing, like other channels). |
| `DISPATCH_HOUR` | `21` | Riyadh hour for the nightly auto-post. |
| `DISPATCH_DRYRUN` | `0` | `1` = log instead of post (safe testing). |
| `PUBLIC_BASE_URL` | (existing) | Needed for the absolute button link. If unset, `post_dispatch` still posts the embed with a **copyable text block** and logs a setup warning (graceful degradation). |

## 7. Error handling / edge cases

- **`PUBLIC_BASE_URL` missing** → no button; embed includes the WhatsApp text in a copyable code
  block + a one-line "set PUBLIC_BASE_URL for one-tap sending" note. Never crashes.
- **Team has a token but no apartments today** → no message for that crew (no noise).
- **Apartment needs cleaning but no `cleaning_team`** → safety-net message (§4.1.7).
- **Apartment in a crew but not OujaCT-flagged** → not included (dispatch mirrors OujaCT scope);
  documented, not a bug. If the owner wants a non-OujaCT unit dispatched, they flag it `oujact`.
- **Redeploy near 21:00** → daily idempotency guard prevents double-post.
- **Data changes between 21:00 post and a later button tap** → the redirect rebuilds fresh, so the
  crew always gets the current list (desired).
- **Arabic formatting** kept simple (Latin digits acceptable; Arabic weekday names via a small map).

## 8. Testing (before "done", per CLAUDE.md routine)

Standard: `py_compile`, `pyflakes bot.py`, `node --check finance/static/erp.js` (unchanged but part
of routine), `unittest discover`. Plus **new synthetic-data unit tests** (`tests/test_dispatch.py`):

1. **Date resolution** — `_dispatch_resolve_date(None)` returns today before noon / tomorrow after
   (inject a fixed `now`); explicit `"today"`/`"tomorrow"`/ISO honored.
2. **Grouping + safety net** — feed fake turnovers across 2 crews + 1 unassigned; assert each crew
   bucket and that the unassigned one lands in `unassigned`.
3. **WhatsApp text** — early-departure sorts first; `checkin_today` shows `(عاجل)`; no-checkin path;
   count correct.
4. **WhatsApp URL** — phone present → `wa.me/{digits}`; absent → `api.whatsapp.com/send`; text is
   URL-encoded (spaces/newlines/Arabic).
5. **Empty day** — no turnovers → the "لا يوجد تنظيف" branch, no crew messages.

## 9. Explicitly OUT of scope (YAGNI)

- No automated WhatsApp sending / WhatsApp Business API.
- No new crew or apartment data model (reuse existing `cleaning_team`).
- No changes to the midnight OujaCT builder, the `/oujact-route` page, or the roster.
- No read-receipt / delivery tracking from WhatsApp (impossible without the Business API).
- No per-apartment individual messages (crew-level only, by owner's choice).

## 10. Rollout

Additive and reversible. Ship with `DISPATCH_DRYRUN=1` first to eyeball the messages in logs /
a test post, confirm crews+phones are set, then flip `DISPATCH_DRYRUN=0`. `DISPATCH_ENABLED=0`
fully disables. Tell the owner in plain language: "new `dispatch` channel, posts each night at 9,
tap the green button to WhatsApp each crew; `!ouja dispatch` to send on demand."
