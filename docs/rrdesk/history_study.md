# RR history study — what really happens between Sam and the team (2026-10-24)

Read-only. Redacted (PDPL): staff appear as role labels (موظف-1 … موظف-9, «المالك» = the owner),
guests as «الضيف», reservation codes as HMXXXX; no phone, email, IBAN or national id. Raw data
stays in the git-ignored `.rrdesk_study/`.

## Source

| | |
|---|---|
| How | The owner's logged-in Discord in Chrome (brief §4.1 source 2), read-only page reads. No bot token or Railway CLI existed on the build machine, so source 1 (`tools/rr_history_export.py`) is shipped for later and `/rrdesk-study` repeats this inside the bot after deploy. |
| Rooms | 60 — `RR` (29), `RR ٢` (17), the «📦 أرشيف ١-٤» archive (14: old Ticket Tool rooms `ticket-53…81`, `تعويضات`, closed `rr-0xx`). 54 of them have Sam in them. |
| Messages | 1,910 (736 from Sam, 415 from the bot) |
| Dates | 2025-12 → 2026-10-24; volume is rising fast (Jun 171 · Jul 228 · Aug 228 · **Sep 702** · Oct 541 in 24 days) |
| Not read | `rr-general` loaded 132 messages but not its very beginning (a general chat, not a ticket). The `rr-tickets` panel has no conversations. |
| Sam | Discord id `1494059651032158409` («Sam1989»), the only English writer; shipped as the last-resort default for `sam_ids`. |

## Requests

How a request was recognised: `rrdesk.study.looks_like_request` (questions, «send / share / need /
where / can you / please …», minus thanks and pings). On the 122 hand-labelled golden messages it
scores **96% precision, 82% recall**, so the counts below are close to the truth.

| | |
|---|---|
| Sam's requests | **247** |
| Never got a team reply in the room | **13** |
| Waited more than 24 working hours | **37** |
| Sam had to ask again before any reply (re-ask) | **57** |
| Sam's pure follow-ups («following up», «hello @…», «any update?») | **64** messages |
| Rooms where Sam was the last to speak for 2+ days | **26** |
| Voice notes in Sam's rooms | 8 |

### Top kinds of request
other / general 153 · photos 39 (almost always «before check-in photo, dated») · info 38
(«what is 715.3?», «who paid for the repair, Ouja or the owner?») · invoice 26 · video 6 ·
guest chat 3 · ops report 2 · Airbnb screenshots 1.

### Timing (working minutes, 11:00 → 01:30; wall-clock in brackets)

| | n | p50 | p60 | p75 | p90 |
|---|---|---|---|---|---|
| First team reply | 234 | 27 | 91 | 481 | 1,481 |
| (wall-clock hours) | | (0.6 h) | (1.8 h) | (16 h) | (44 h) |
| Delivery | 218 | 43 | 116 | 581 | 2,419 |

By ask — median delivery: photos 44 min (p90 **138 h**), invoice 79 min (p90 64 h), info 76 min
(p90 78 h), video 180 h. The median is fine; **the tail is the problem** — one request in four
waits a full working day.

By person — median first reply (working minutes), replies counted: موظف-1 18 (92) · المالك 1 (18)
· موظف-6 11 (17) · موظف-3 36 (27) · **موظف-2 319 (35)** · موظف-4 38 (8) · موظف-5 44 (34). Internal
only: the dashboard never ranks people; it shows each person against the fixed target.

## Silence patterns (what "ignored" looks like here)

1. **The photo that never comes.** Sam asks for the dated before-check-in photo; the team answers
   something else (a price, «I sent it on WhatsApp»); Sam re-asks for days. (ticket-70: 10 days.)
2. **The question nobody owns.** «who handles the repair, Ouja or the owner?» asked to two people
   at once — each assumes the other will answer.
3. **Night asks.** Sam is most active late evening; the reply comes next afternoon.
4. **Answers outside the room.** «I sent it on WhatsApp» — the claim evidence never lands where
   Sam can attach it.
5. **The team writes English to Sam.** 506 of 566 staff messages in Sam's rooms are English; only
   60 Arabic, and 2 of Sam's messages ask what an Arabic line meant. Translation lets the team
   write in their own language.

## Language

Staff → Sam: 506 English / 60 Arabic messages. Bot messages in Sam's rooms are mostly Arabic
(cards, «لقيت الحجز في Hostaway», close-out lines, nudges) — the reason bot Arabic is translated.
Bot noise that is NOT translated: the English «RR TICKET» (64), the WhatsApp copy block, pins.

## Calibration (brief §4.5 — applied, not loosened)

| | Rule | History | Result |
|---|---|---|---|
| **Response SLA** | p60 of first reply, rounded to 15 min, clamped 30-120 | p60 = 90.6 | **90 working minutes** |
| **Delivery SLA** | p60 of delivery, rounded to the hour, clamped 4-16 h | p60 = 115.5 (2 h) | **4 working hours** (the floor) |
| Urgent | fixed | — | 30 min / 3 h |
| How far the team is from the new standard today | | | **40% of replies and 34% of deliveries** would have breached |

The breach shares are above 35%, so — per the brief — the computed numbers are kept and the
percentage is reported as the distance to the standard. The detector threshold could not be
measured offline (no API key on the build machine): detection ships in **confirm** mode until
`/rrdesk-study` grades Haiku on the golden set.

## Cost estimate (translation)

Last 30 days: 677 messages in RR rooms → 135 trivial (emoji / numbers / pings), 32 bot English,
26 free phrases → **≈ 482 paid calls/month** (228 of them Sam's, with classification). At Haiku
4.5's published $1 / $5 per million tokens (~750 in / 90 out per call, ~1,000 / 180 for Sam):
**≈ $0.74 ≈ 2.8 SAR per month.** Even at triple today's volume it stays under 10 SAR. The cache
and phrase table only lower it. The daily cap (1,500 calls) is a safety net, not a budget.

## Five rooms, before and after (from `python3 -m rrdesk.replay`)

1. **ticket-70.** Before: Sam asked for the before-check-in photo and invoice on 06-04 at 16:07; a
   price came back 12 minutes later, the photos only on 06-14, after four follow-ups. After: the
   price reply acknowledges the request, D1/D2 remind the owner that evening, and at 00:07 (twice
   the 4-hour delivery time) it is a miss → a private notice, no warning. Sam's «can i have the
   before check-in photos?» next morning is logged as a re-ask on the same request, not a second one.
2. **rr-077.** Before: «what is the 715.3 and 485.3?» and «I need to submit this now» got no
   answer. After: both tracked, the owner pinged twice, a miss each; «Unfortunately, there is no
   invoice» counts as an answer («ما عندنا»), so no warning.
3. **rr-055.** Before: «carpet invoice» + «and any other photos?» sent a second apart late at night.
   After: one request (burst merge), one miss, a notice — not a warning for one late morning.
4. **rr-074.** Before: Sam asked eight times over three days for the photo of the broken table; it
   never came. After: two misses in the same week → **one would-be warning** in the dry-run log
   («commission would become 90%») — the only case in the six rooms that reaches money.
5. **rr-006.** Before: the reservation code was wrong; Sam asked three questions over two weeks.
   After: each question owned and timed; three notices across different weeks, no warning.
