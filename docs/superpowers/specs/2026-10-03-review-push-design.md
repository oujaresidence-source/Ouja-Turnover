# رفع التقييم — Review Push · design spec

Owner-approved 2026-10-03 (Faisal). Package: `reviewask/`. Topic prefix: `ouja-rv:`. Tables: `rv_*` in brain.db.

## 1. Goal

Every Ouja apartment has an Airbnb guest rating **above 4.75**. Every checkout from a weak apartment gets
its own Discord ticket room. The room drives two human touches with one-tap tools:

1. a WhatsApp message on checkout day
2. a phone call the next evening if no review has arrived

Every press is recorded against the person who pressed it, and the room closes itself when the review lands.

Success metric (kill test after 45 days): **review rate** (reviews ÷ checkouts) on flagged apartments
vs their own previous 90 days, plus the share of 5★ among reviews gained. If review rate does not rise,
the program is not working, whatever the activity numbers say.

## 2. Owner rulings (absolute — do not "improve" them away)

| # | Ruling |
|---|---|
| R1 | Tickets are **Discord channels (rooms)**, one per reservation — not threads, not forum posts. |
| R2 | **Buttons carry text, no emoji.** Meaning comes from the label + button colour (success / danger / secondary / primary). Embeds and guest messages may use emoji; button labels may not. |
| R3 | A maintenance ticket opened from this flow must **say it came from a review call** — title prefix «من مكالمة تقييم», a field «المصدر: مكالمة تقييم» with a link back to the review room, the guest's words verbatim, and who called. |
| R4 | The WhatsApp message and the call script are **owner-written** in an editor ("window"). There is a dashboard editor with live preview, plus a Discord modal via `/رسالة-التقييم`. Both write the same stored template. Pressing «فتح واتساب» opens WhatsApp on the guest's number with the message already typed. |
| R5 | A command `/تقييمات-بكرة` opens tomorrow's rooms **now** (~12 h ahead). The bot also does it automatically at 00:05 for anything missing, so a forgotten command loses nothing. |
| R6 | A tracking system modelled on Checkout Watch «طلع الضيف؟»: a live board, a 30-minute monitor report naming people, a daily summary, a private report command, and a dashboard tab. |
| R7 | **Closed review rooms are deleted 7 days after closing.** The full record (events, notes, the room's message transcript) is saved to the DB first and stays visible in the dashboard forever. This is the owner's explicit approval (2026-10-03) for these rooms ONLY: `ouja-rv:` topic + `rv_tickets` row closed ≥ 7 days + channel id match. Nothing else is ever deleted by this package. |
| R8 | The 10% discount stays in the message — owner's decision. The default template words it as an unconditional thank-you for the stay, separate from the review request, and the owner may edit it freely. The code must never hard-code any discount or offer. Template text is 100% owner-controlled. |
| R9 | Ships **OFF**. Nothing posts until an admin runs `/تقييمات-تشغيل`. Stored switch > env `REVIEWASK_LIVE` > 0. |
| R10 | Never push to GitHub without the owner's word (CLAUDE.md). |

## 3. Which apartments are in the program («الشقق الضعيفة»)

Pure function `engine.apartment_status(reviews, overrides, open_tickets)` → per listing:

- **Source:** Hostaway `/v1/reviews`, guest-to-host only, Airbnb channel only.
  - BEFORE trusting the filter, print the distinct values of `type` (and `channelName`) seen on live data and record them in the plan. `fetch_reviews_from_hostaway` today does not filter by type, and the shipped insights file mixes in `respect_house_rules`, which is a host-to-guest category.
  - If no `type` field exists, document the fallback you chose and test it.
- **Rating:** `rating_raw / 2` as a float (Hostaway is out of 10). The existing normaliser rounds to an int — do NOT use `rating`. Airbnb's displayed overall rating is the plain average of the overall scores (sub-categories don't enter it).
- **Exact integer math on Hostaway's 10-point scale** (no floats in the decision): n = guest reviews, R = sum of `rating_raw`. avg > 4.75 ⇔ `2R > 19n`.
- **In the program** when `2R <= 19n` (avg ≤ 4.75), OR the listing has fewer than 3 guest reviews (Airbnb shows no rating until 3 — new units need reviews most). **Out** when `2R > 19n` with ≥ 3 reviews.
- **Manual pin** (dashboard, admin only): `force_in` / `force_out` per listing, with a reason. This exists because Hostaway's number can differ from what Airbnb shows; the dashboard shows both "our computed" and "pinned".
- **Reviews needed** (5★ = 10): smallest k with `(R + 10k) / (n + k) > 9.5` → `k = 19n − 2R + 1` when `2R <= 19n`, else 0. Unit-test it. Examples: n=10, R=90 (4.50) → 11; n=47, R=415 (≈4.41) → 64; n=4, R=38 (4.75 exactly) → 1.
- **Open tickets:** count of open maintenance tickets on the listing (`_dtk["tickets"]` kind `maint` not closed, plus open dashboard `_tickets` with that `lid`). Shown on the board and the dashboard as a risk column. It does not by itself put an apartment in the program (see §4 care mode).

Reality check from the shipped `reviews_insights.json` (May 2026, 58 units): 18 below 4.75. Live numbers will differ.

## 4. Which reservations get a room

A confirmed reservation (`status in CONFIRMED_STATUSES`) departing on day D gets a room if either:

- **review mode** — its listing is in the program; or
- **care mode** — a maintenance ticket on that listing was open or created during the stay (arrival..departure), or the stay has a recovery ticket. This applies whatever the apartment's rating.

Skips are listed (never silently dropped) in the `/تقييمات-بكرة` reply and the board: listing out of program, reservation cancelled, owner/blocked stay, non-Airbnb channel (direct bookings via `_finance_channel` are skipped unless the owner adds them later), duplicate.

Detection reads a targeted Hostaway departure window (`_ha_reservations_window("departureStartDate", "departureEndDate", …)`), never `get_reservations_cached()` (CLAUDE.md trap 4).

## 5. The room

- **Category** «طلبات التقييم», spilling into «طلبات التقييم ٢…» via `_make_channel_spill` (the 50-per-category cap is certain).
- **Name** `تقييم-<unit-slug>-<guest-first-name>` (≤ 90 chars).
- **Topic** `ouja-rv:<reservation_id> lid:<lid> seq:<n>`.
- **Anti-duplicate**, same as directpay: `UNIQUE(reservation_id)` in `rv_tickets` + `_once_claim("reviewask:open:<id>")` (released on failure) + rebuild from channel topics across `_category_family` on every tick.
- **Card** (embed, Turnover-card family layout, Arabic):
  - الشقة
  - الضيف
  - الخروج
  - المسؤول — from `_cw_cover(lid, day)`, the Employee Calendar for the day of the ACTION, so a call on day+1 goes to whoever covers that day
  - تقييم الشقة الحالي + كم تقييم ٥ نجوم ناقص
  - الوضع — review / care
  - الحالة
  - تنبيه — when the stay had a ticket: «الضيف كان عنده بلاغ صيانة أثناء الإقامة: اتصل اطمئنان أول، لا تطلب تقييم قبل ما تتأكد إنه راضي»
- Ticket rooms are visible to the ops department like other tickets (per the 2026-10 tidy rules). Copy the parent category's overwrites and never widen them.

## 6. Timeline and state machine (engine.py, PURE, TDD-locked)

States:
- **Open:** `waiting` → `wa_due` → `wa_sent` → `call_due` → `call_retry`, plus `care_due` (care mode)
- **Terminal:** `reviewed` · `promised_expired` · `declined` · `wrong_number` · `no_answer_final` · `complaint` · `expired` · `cancelled` · `void`
- **Waiting-for-review (open):** `promised`

| When (Riyadh) | Review mode | Care mode |
|---|---|---|
| room opened (cmd / 00:05 / catch-up tick) | `waiting`, card posted, **no mention** | same |
| D 17:00 | → `wa_due`: mention responsible; buttons: «فتح واتساب» (link) · «أرسلت الرسالة» · «الضيف رد» · «ما فيه رقم» | → `care_due`: mention; call buttons (§7) with outcome «راضي» unlocking the WhatsApp step |
| D 18:00, D 19:30 | reminder if still `wa_due` | reminder if still `care_due` |
| D+1 call time (§8) | if no review and not replied → `call_due`, attempt 1: mention + call buttons | care not done → stays due, counts as staff miss |
| call time +45 min, 21:30 | reminders | reminders |
| «ما رد» or «كلمني بعدين» | → `call_retry` at the next day's call time; attempt 2 is the LAST | same |
| 2nd «ما رد» | → `no_answer_final` (close) | same |
| review detected for this reservation | → `reviewed` (close) from ANY open state incl. `waiting`/`promised`; post the stars; if < 5★ add «تقييم أقل من ٥» to the board and summary | same |
| D+13 23:59 | anything open → `expired` (`promised` → `promised_expired`). Airbnb closes reviews 14 days after checkout | same |
| Hostaway cancellation / departure moved | → `cancelled` with a note | same |

Rules:
- **Staff misses don't burn guest attempts.** If the call window passes (22:00) with no press, the attempt is NOT consumed. The board marks a staff miss against the responsible person, and the same attempt rolls to the next day's call time.
- **Guest-facing silence:** no pings or reminders 22:00–13:00, except the silent opening card. Cards show «لا تتصل بعد ١٠ مساءً». CST rule 10-4-4 forbids promotional calls/messages 22:00–09:00, and 01:00–12:00 in Ramadan; we use 22:00 as the ceiling all year.
- **First-final-wins** via a conditional UPDATE under a lock (`checkout/db.transition` pattern). A late press is told «انحفظت قبلك من …».
- **Every transition** writes an `rv_events` row: who (Discord id + calendar name), what, when, note.

## 7. Buttons (text only — R2)

Persistent views with static custom_ids, one `on_interaction` listener (`_rv_interaction`) that finds the row by message id, so buttons survive redeploys (Checkout Watch pattern).

**WhatsApp stage**

| Label | Style | Effect |
|---|---|---|
| فتح واتساب | link | `/rv/<token>` → 302 to `wa.me/<intl>?text=<rendered template>`; the hit is logged as `wa_opened` |
| أرسلت الرسالة | success | → `wa_sent` |
| الضيف رد | primary | modal with a choice: «بيقيّم» → `promised` · «عنده ملاحظة» → complaint modal · «ما يبي» → `declined` · «رد بس ما قال شي» → stays `wa_sent` with a note |
| ما فيه رقم | secondary | → skips WhatsApp; offers «رسالة Airbnb» (link to the Airbnb conversation via `guest_conversation_links`); the call stage still opens |

**Call stage**

| Label | Style | Effect |
|---|---|---|
| قيّم | success | → `promised` (closes as `reviewed` when the review lands; otherwise `promised_expired`) |
| وعد يقيّم | success | → `promised` |
| ما رد | secondary | attempt += 1; retry next day or `no_answer_final` |
| كلمني بعدين | secondary | → `call_retry` next day, does NOT consume an attempt (once only, then it behaves as «ما رد») |
| عنده ملاحظة | danger | complaint modal (§9) → `complaint` |
| ما يبي يقيّم | secondary | → `declined` |
| الرقم غلط | secondary | → `wrong_number` |
| فتح واتساب | link | always available in the call stage too |

**Care stage:** «راضي» (success → unlocks the WhatsApp stage at once) · «عنده ملاحظة» · «ما رد» · «كلمني بعدين» · «الرقم غلط».

A link button can't know who pressed it, so the WhatsApp text is signed with the RESPONSIBLE person's name, and «أرسلت الرسالة» records the actual presser.

## 8. Call time

`engine.call_time(date)`:
- **20:00** Sep–Apr
- **20:45** May–Aug, when Riyadh Isha moves to ~20:05–20:20
- **21:30** in Ramadan, after Taraweeh

Ramadan is detected with `hijridate` when importable. Otherwise use env `REVIEWASK_RAMADAN=YYYY-MM-DD:YYYY-MM-DD`. Env `REVIEWASK_CALL_AT` (HH:MM) overrides everything. WhatsApp time is env `REVIEWASK_WA_AT` (default 17:00). All values are read at call time.

Rationale: after Isha, before the 22:00 ceiling. This is a strong inference — there is no Saudi study on consumer call-answer rates by hour. Keep it a setting.

## 9. Complaint → maintenance ticket (R3)

The «عنده ملاحظة» modal has:
- «وش قال الضيف؟» — required, 10–1000 chars
- «وين المشكلة في الشقة؟» — optional
- urgency select

Submit calls `_maint_open_ticket(interaction, lid, unit, urgency, category, summary, details, location, access)` with these additions (backward-compatible kwargs on `_maint_open_ticket`):

- `summary` = «من مكالمة تقييم — {unit} — {guest first name}» (≤ 120)
- `details` = the guest's words verbatim + «اتصل: {presser}» + «رقم الحجز: {res_id}» + «تاريخ الخروج: {D}»
- new kwarg `origin="review_call"` → `_ticket_create(..., source="review", source_ref="rv:<res_id>")` (the `"review"` source already exists in `_ticket_create`'s whitelist) and an extra card field «المصدر» = «مكالمة تقييم» with `<#review_room>`
- the review room gets a reply linking the new maintenance room, and the row → `complaint`

Existing callers of `_maint_open_ticket` must be byte-for-byte unaffected (default kwargs). Add a test.

## 10. Templates (R4, R8)

Stored in `rv_settings` as JSON `{ar, en, call_script, updated_by, updated_at}`. Seeded from `reviewask/templates.seed.json` on first boot only.

- **Placeholders:** `{الاسم}` (guest first name, `checkout.texts.guest_first` logic) · `{الموظف}` (the responsible person's calendar name) · `{الشقة}` (unit name without the «Ouja |» prefix) · `{رابط_التقييم}`. Unknown placeholders are left visible and flagged in the editor preview — never crash.
- **Review link** default `https://www.airbnb.com/users/reviews`, env `REVIEWASK_REVIEW_URL`. Verify on a phone during the demo that it lands on "reviews to write"; if not, set the env to `https://www.airbnb.com/trips`.
- **Language:** phone normalised by `_wa_from_phone` starting `966` → `ar`, otherwise `en`. If `en` is empty, use `ar`.
- **Editors:**
  - Dashboard tab «رفع التقييم» → «نص الرسالة»: three textareas, live preview with a sample guest, the char count of the encoded wa.me URL, save. Admin only.
  - Discord `/رسالة-التقييم`: a modal with 3 paragraph inputs (Discord max 4000 chars each) prefilled with the current text. Admin only.
  - Both write through ONE function `db.save_templates(...)`, which keeps the previous version in `rv_template_history`.
- **Redirect:** the message goes through our `/rv/<token>` 302 redirect (Discord caps button URLs at 512 chars — the bug Checkout Watch already hit).

## 11. Tracking (R6) — mirrors Checkout Watch

- **Board** «متابعة-التقييمات»: one message set, edited in place every tick (≤ 1900 chars per chunk). Sections:
  - اليوم: واتساب لازم ينرسل
  - مكالمات الليلة
  - بانتظار التقييم
  - انقفلت اليوم + السبب
  - تقييمات أقل من ٥
  - الشقق تحت ٤.٧٥ (rating · ناقص كم · تكتات مفتوحة)
- **30-min report → «غرفة-المراقبة»** (the same room as `_cw_monitor_channel`) from 17:00 to 22:00, naming the responsible person and minutes overdue. Slot latch persisted in `rv_settings` (no double post on redeploy). Silent when nothing is due.
- **Daily summary at 22:00** into the board: reviews gained today and their stars, WhatsApp sent X/Y, calls done X/Y, staff misses, complaints opened.
- **`/تقرير-التقييمات`** (ephemeral) and the prefix version (DM): per person — sent rate, call rate, reviews gained, average stars gained, misses; per apartment — rating then vs now, reviews needed.
- **Dashboard tab «رفع التقييم»** (cat_ops, `_ROLE_READ_RULES` / `_ROLE_WRITE_RULES` permission tab; follow the permits tab pattern: real JS file `reviewask/static/reviewask_tab.js` + ≤ 15-line backslash-free stub in `DASHBOARD_HTML`). Sub-views:
  1. الشقق — table + manual pin
  2. التكتات الحية
  3. الأداء — per person
  4. الأرشيف — closed tickets with events and the saved transcript, kept forever
  5. نص الرسالة — the editor

## 12. Review detection

`reviews_refresh_loop` is daily — too slow. Add a targeted pull every 30 min: `/v1/reviews` first 2 pages sorted `departureDate:desc`. Match on `reservationId`, then merge into `_reviews` the same way `refresh_reviews` does.

Matching a review to a room closes it (§6). Because Airbnb reviews are double-blind, a guest's review reaches Hostaway only after BOTH sides review or day 14. The card's footer and the dashboard state this. The «قيّم» button is the fallback signal. Do not change Hostaway's auto-review settings from code.

## 13. Room deletion (R7)

Hourly job `flow.sweep_closed(now)`. For each `rv_tickets` row with `state` terminal AND `closed_at <= now − 7d` AND `deleted_at IS NULL`:

1. fetch the channel by the stored id
2. assert its topic starts with `ouja-rv:<same reservation_id>` — otherwise refuse, log, and mark `delete_refused`
3. save the transcript (all messages: author display name, time, content, embed text, attachment URLs; ≤ 500 messages) into `rv_transcripts`
4. delete
5. set `deleted_at`

A missing channel → `deleted_at` with note «كانت محذوفة». "Couldn't check" is never treated as deleted. Max 10 deletions per run, 1 s apart.

`ops_tidy` must never archive or lock `ouja-rv:` rooms. Check `ops_tidy_rules.py` and add the exclusion + a test if needed. Do NOT call `archive_closed_channel` from this package.

## 14. Commands

Slash command + `!ouja` prefix fallback, like Checkout Watch. Admin = `_can_delete_channels`; ops leads may run the first two.

| Command | Does |
|---|---|
| `/تقييمات-بكرة` (`reviews-tomorrow`) | opens rooms for tomorrow's departures now; replies with the counts + the skip list |
| `/تقييمات-اليوم` (`reviews-today`) | same for today (late bookings / first day) |
| `/تقييمات-تشغيل` · `/تقييمات-ايقاف` | stored switch; stopped = tick returns at once, buttons still record |
| `/رسالة-التقييم` | the template modal (admin) |
| `/تقرير-التقييمات` | the private report |

All go through an always-answering wrapper (`_cw_answer` pattern), and blocking work runs on the package's own pool (`run_blocking`), never `asyncio.to_thread`.

## 15. Architecture (house pattern)

```
reviewask/
  __init__.py      wire / register_routes / bootstrap (never raises into boot)
  host.py          the ONE bridge; never `import bot`
  config.py        env, read at call time
  engine.py        PURE: apartment_status, reviews_needed, eligibility, next_action(row, now), call_time, render_template, language
  db.py            rv_tickets, rv_events, rv_links, rv_settings, rv_template_history, rv_transcripts, rv_overrides (brain.db)
  flow.py          tick, open_rooms(day), answer_*, sweep_closed, board, reports
  texts.py         Arabic strings + card dicts (Discord embed shape)
  routes.py        /rv/<token> (public), /api/reviewask/* (login + permission)
  static/reviewask_tab.js
  templates.seed.json
  GATES.md
```

`bot.py` gets only wiring:
- `_rv_wire()`, `_rv_interaction`, the commands, `reviewask_loop` (every 2 min, guarded and staggered)
- the `_maint_open_ticket` kwargs
- the 30-min review pull
- NAV_DEF entry + labels in both `labels.ar` and `labels.en`
- permission rules

Python 3.9-compatible syntax (no `X | None`, no `match`). Zero backslashes in `reviewask/*.py` and in the tab stub.

## 16. Env (defaults correct — the owner never opens Railway)

| Variable | Default |
|---|---|
| `REVIEWASK_ENABLED` | 1 |
| `REVIEWASK_LIVE` | 0 |
| `REVIEWASK_THRESHOLD` | 4.75 |
| `REVIEWASK_MIN_REVIEWS` | 3 |
| `REVIEWASK_WA_AT` | 17:00 |
| `REVIEWASK_CALL_AT` | auto |
| `REVIEWASK_MAX_CALLS` | 2 |
| `REVIEWASK_WINDOW_DAYS` | 14 |
| `REVIEWASK_QUIET_FROM` | 22:00 |
| `REVIEWASK_QUIET_TO` | 13:00 |
| `REVIEWASK_DELETE_AFTER_DAYS` | 7 |
| `REVIEWASK_CATEGORY` | طلبات التقييم |
| `REVIEWASK_BOARD_CHANNEL` | متابعة-التقييمات |
| `REVIEWASK_REVIEW_URL` | https://www.airbnb.com/users/reviews |
| `REVIEWASK_RAMADAN` | empty |
| `REVIEWASK_OPEN_AT` | 00:05 |

## 17. Out of scope (v1)

- Sending WhatsApp automatically (there is no WhatsApp API — the human taps).
- Booking.com / direct stays.
- Changing Hostaway auto-review settings.
- Any AI scoring.
