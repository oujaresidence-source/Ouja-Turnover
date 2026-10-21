# «تسليم الرموز» — House-rules "I agree" + manual door-code release

Status: APPROVED by the owner 2026-10-21 (incl. the three decisions in §6).
Branch: `feat/agree-gate` (worktree `ouja-wt-agree`, cut from `origin/main` 3308eb9).

## 1. Why

Airbnb's house-rules policy for **bookings made on or after 2026-11-20** bans separate
contracts, fines, and rules introduced after booking (a message may only *remind* of rules
already on the listing). Today 34 of our 55 Hostaway listings send a Hostaway rental-agreement
e-sign link, and the door code is released automatically only once it is signed. That
contract step has to go.

## 2. What the owner decided (2026-10-21)

- The guest gets the house rules in the chat and is asked to reply **"I agree to the house
  rules" / «أوافق على قواعد الشقة»**.
- **A human releases the code**, not the bot: the employee who covers that unit *that day*
  (Employee Calendar) reads the reply and sends the code. The owner considers this more secure.
- **Not tied to Hostaway's "agreement signed" status** in any way, and the bot never decides
  whether a reply counts as agreement.
- **Only the listings that use the agreement today** (the 34), not all 55.
- The bot helps the human: a daily Discord list per covering employee, a
  «✅ وافق وأرسلت الرمز» ("agreed, code sent") button, and an alert 2 hours before check-in
  if a code has not been released.

## 3. What exists today (measured 2026-10-21, read-only)

Hostaway automations involved:

| Id | Name | What it does | Listings |
|---|---|---|---|
| 288752 | rental agreement | Sends `{{rental_agreement_link}}` **1 day before** check-in, all channels | 34 |
| 427132 | Doorcodera | Sends `{{door_code}}` **3 h before** check-in, *condition: agreement = Signed* | 28 |
| 438108 | arrival is less than an hour away | Re-sends the signing link 60 min before, *condition: Not signed* | 30 |
| 273042 | Door Lock Code | Sends `{{door_code}}` to the 8 «-O» Al-Nuzha units, no agreement | 8 |

Irregularities found:
- 7 listings get the agreement link but no automatic code (القيروان-D7, B03, B02, TWN 13B,
  11B Royal, 4101, i04). Their codes are already sent by hand.
- **103 NRJS** is set to send the code only after signing, but never gets the agreement link.
  Its code can never go out automatically.
- 12 listings have neither.
- The Hostaway listing **House rules** field (and, for C2 NFL, the description) still carries
  the 4,000 SAR fine and the "Mandatory Rental Agreement" line. Hostaway can push that text
  back to Airbnb.

Bot side (`origin/main`):
- `check_agreement_reminders` / `_check_agreement_for_one` (bot.py ~3025–3175) re-sends the
  signing link 1 h before check-in. After check-in it escalates "code not sent", but **skips
  that escalation while the agreement is unsigned**. Once nobody signs anymore, the safety net
  for these units would go silent.
- Musaed's code-question context (bot.py ~12880–12960) tells guests "the code is sent
  automatically the moment you sign".
- `build_update_rows` (bot.py ~3824) and the monitoring-room snapshot (~74386) show a
  "signed" flag that would read ❌ for every gated unit.
- Who covers a unit on a date: `schedule.coverage.cover_for_listing_id(lid, date_iso)`.
  Employee → Discord id: the ops identity map (`ops.notify._id_map`, layered assignments.json <
  env < typed). Both already exist and are used by OujaCT / recovery.

## 4. The design

### 4.1 Guest side (Hostaway, done with the Chrome extension, one approved change at a time)

1. **Rewrite automation 288752** into the house-rules message below. Same 34 listings, all
   channels, **plus 103 NRJS**. **Trigger changes to "At reservation"** so the guest has the
   most time to reply (owner decision §6).
2. **Turn off 438108** (it re-sends the signing link).
3. **Turn off 427132 Doorcodera** (the code no longer goes out automatically for these units).
4. **Create a saved message template «🔑 كود الدخول / Door code»** containing `{{door_code}}`.
   The employee opens the guest's chat in Hostaway and inserts it with one click. Hostaway fills
   in the guest's code, so the employee never has to look it up and the bot never handles the
   code. **First tested on one real booking** before anyone relies on it.
5. **Fix the House rules field** in Hostaway on the 34 listings (remove the fine and the
   contract line; C2 NFL's description too). On Airbnb, the owner pastes the corrected
   "Requests during the stay" text; guest count goes in the *Max overnight guests* rule.
6. 273042 (Al-Nuzha) is untouched.

House-rules message (from the owner's WhatsApp draft; the fine is removed, everything else kept):

```
حياك الله {{guest_name}} 🤍
أهلاً بك في عوجا، سعداء باستضافتك.

قبل وصولك نذكّرك بقواعد الشقة:
1. الشقة في مجمع سكني عائلي هادئ، للسكن فقط — مو شاليه ولا استراحة ولا مكان حفلات أو مناسبات.
2. السكن فقط للأشخاص المسجّلين في الحجز.
3. نرجو الهدوء خصوصاً بالليل — بدون موسيقى عالية أو سماعات خارجية.
4. الوقوف في موقفك المخصص فقط.

مخالفة القواعد قد تؤدي لإلغاء الحجز وإبلاغ Airbnb والجهات المختصة.

فضلاً رد على هالرسالة بـ: «أوافق على قواعد الشقة»
وبعدها نرسل لك كود الدخول قبل وصولك.

شكراً لأنك تحافظ على هدوء عوجا 🌿
فريق عوجا

—

Hi {{guest_name}},
Welcome to Ouja! We are happy you are staying with us.

Please read our house rules one more time:
1. This home is in a quiet family area. It is only for staying. It is not a chalet, a resort or a place for parties or events.
2. Only the people on your booking can stay.
3. Please keep it quiet, most of all at night. No loud music. No outside speakers.
4. Park only in your own parking spot.

If a rule is broken, your booking may be cancelled. We will also tell Airbnb and the authorities.

Please reply to this message with: "I agree to the house rules"
We will send your check-in code before you arrive.

Thank you for keeping Ouja calm and peaceful 🌿
The Ouja team
```

### 4.2 Staff side (the bot), a new package `codegate/`

Same shape as the other packages (`decor/`, `checkout/`, `ops/`): `db.py`, a pure `engine.py`,
`host.py` wiring, plus the Discord view in bot.py.

**Which units.** `codegate/units.json` holds the gated listing ids (the 34). A copy in
`$STATE_DIR/codegate_units.json` wins if present (the `decor_packs.json` pattern), so the list
can change without a deploy. 103 NRJS is included (§6), making 35 units.

**The daily list.** At **09:00 Riyadh** the bot posts in a dedicated channel
`#تسليم-الرموز` (fallback: `#escalations` if Discord refuses a new channel, which has
happened before at the 500-channel cap):
- one header per covering employee, mentioning them (`@نورة — ٣ وصول اليوم`);
- one card per arriving guest on a gated unit, with: unit, guest, check-in time, Hostaway chat
  link, and the guest's replies since the house-rules message, **quoted word for word** (up
  to 3 messages, 300 characters each). The bot never labels a reply as agreement;
- the button **«✅ وافق وأرسلت الرمز»**.

**Who covers.** `cover_for_listing_id(lid, today)`, then the permanent owner as a fallback.
If nobody resolves, the card is tagged to the ops role and says "no coverer in the calendar"
so it cannot silently belong to nobody.

**Refresh.** Every 10 minutes the bot edits the existing cards with new guest replies, and
adds cards for same-day bookings that appear after 09:00. Cards are edited, never re-posted.

**The button.**
1. Pressing it opens a private ask-again step (the «شقتك جاهزة» two-step pattern): «الضيف
   كتب أوافق في المحادثة، وأرسلت له الرمز من Hostaway؟» ("Did the guest write I agree in the
   chat, and did you send the code from Hostaway?") with confirm / cancel.
2. Allowed: that day's coverer, the permanent owner, admins and the ops role. Anyone else gets
   a polite private refusal.
3. On confirm, the card turns green: «أُرسل الرمز ✅ — نورة ١٤:٠٥» (code sent by نورة at 14:05).
   Who and when are stored.
4. **Honesty check:** 15 minutes later the bot looks at the Hostaway chat for a code message
   (the existing `_was_code_sent_recently`). If it sees none, the card says
   «ضُغط الزر بس ما شفت رسالة الرمز في المحادثة ⚠️» ("button pressed, but I don't see the code
   message in the chat") and pings the presser once.
5. Admins get a small «تراجع» ("undo") for a mistaken press. It is logged and never deletes
   history.

**Alerts.**
- **2 hours before check-in**, if not released: post in `#تسليم-الرموز` mentioning the
  coverer and the ops role, plus a high card in `#escalations`. Once per booking.
- **At check-in time**, if still not released: a second high escalation. This replaces the old
  "code not sent" escalation, which goes silent for these units.
- Same-day bookings made later than the 2-hour mark alert immediately on first sight.

**Storage.** One brain.db table `codegate_releases` (reservation id as key: listing,
arrival date, conversation id, card channel/message ids, released by/at, code seen at, alert
stamps, undo by/at). It follows the brain.db rules: no WAL, `closing(connect())`,
`journal_mode=DELETE`. The button finds its booking by the card's message id ("the message id
IS the key", like decor/directpay), so it keeps working after a restart via `bot.add_view`.

**Switch.** `CODEGATE_ENABLED` defaults to **1 in code** (the owner does not edit Railway).
Only staff see what the bot posts, so being on does not change what guests receive.

### 4.3 Changes to existing bot behaviour (gated units only; every other unit untouched)

- `_check_agreement_for_one`: returns early for gated units (`codegate` owns them now), so no
  more signing-link reminders and no double escalation.
- Musaed's code-question context: for gated units it says «الضيف لازم يرد على رسالة القواعد
  بـ"أوافق"، وبعدها الفريق يرسل الرمز» ("the guest has to reply 'I agree' to the rules message,
  then the team sends the code"), plus whether the team has already released it. It never
  promises a time, never mentions a contract, and never writes a code (the firewall stays
  exactly as is). The ANTI-NAG line gets the same wording.
- `/update` and the monitoring room: for gated units the "signed" column shows the release
  status (✅ released / ⏳ waiting) instead of an always-❌ "not signed".

## 5. Rollout

1. **Bot first, while Hostaway still runs the old flow.** The list and buttons go live. For a
   day or two the team sees real arrivals on the list (with codes still going out
   automatically) and we check that every card lands on the right person.
2. **Then the Hostaway switch in one sitting** (§4.1 steps 1–5), each step shown to the owner
   before saving. One booking is tested end to end: rules message → "I agree" → card → template
   → code → green card.
3. **Undo:** turn 288752's old text, 438108 and 427132 back on in Hostaway; set
   `CODEGATE_ENABLED=0` or revert the commit. Nothing is deleted at any step.

## 6. Owner decisions (2026-10-21)

1. **103 NRJS joins the gated list** (35 units): it gets the house-rules message and staff
   release its code. It is added to automation 288752's listings; its Doorcodera assignment
   goes away with 427132 being turned off.
2. **The rules message goes out "At reservation"** (trigger of 288752 changes from 1 day
   before check-in).
3. **Phone agreement must be typed in the chat.** The release button's confirm step asks for
   a written «أوافق» in the conversation; staff ask a phoning guest to type it first.

## 7. Testing

- `engine.py` is pure and test-first: gated filter; coverer grouping incl. the fallback chain;
  reply extraction after the rules-message marker (and never quoting our own message, which
  contains the words "I agree to the house rules"); 2 h / check-in alert timing in Riyadh time,
  including same-day late bookings; status after release / undo.
- View tests: permission matrix; confirm step required; a second press doesn't duplicate.
- Regression: `_check_agreement_for_one` unchanged for non-gated units; Musaed context for
  gated vs non-gated units; firewall code-leak tests still pass.
- Full CLAUDE.md verification routine (py_compile, pyflakes, `node --check`, unittest, esprima
  on DASHBOARD_HTML if touched, which is not planned).

## 8. Out of scope

- Any automatic reading of "I agree" or automatic code release.
- Touching Hostaway's rental-agreement settings or the agreement status.
- The 12 listings with neither message, and Al-Nuzha's 273042.
- Collecting guest IDs (Shomoos), a separate legal question.
