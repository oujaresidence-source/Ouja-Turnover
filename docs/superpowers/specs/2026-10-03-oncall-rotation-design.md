# «المناوبة» — Evening On-Call Rotation — Design

Date: 2026-10-03 · Branch: `feat/oncall` (worktree `ouja-wt-oncall`, from origin/main fd01739)
Status: design approved in conversation; this document awaits the owner's review.

## ملخص للمالك (القرارات اللي اتفقنا عليها)

- **الوقت:** من 5 العصر لين 12 الليل بس. من 12 الظهر لين 5 الكل موجود وما فيه أسئلة حضور. بعد 12 الليل خارج الدوام (رد البوت الحالي).
- **فريق المناوبة:** نوره · ناصر · محمد · عهود · مآثر. **المشرفة: اسيل** (ما تدخل المناوبة أبداً).
- **التوزيع تلقائي وعادل:** الـ7 ساعات تنقسم على الموجودين (ساعة أو ساعتين متصلة)، العدل على الأسبوع، والسلوت الأخير يتدوّر.
- **الجدول ينزل الساعة 12 الظهر لليوم اللي بعده.** التبديل: طلب ← موافقة صاحب السلوت ← يتعدّل، واسيل يوصلها خبر. يتقفل الساعة 3 العصر يوم المناوبة، وبعدها اسيل بس.
- **«موجود؟» كل 15 دقيقة** (أول واحد لحظة بداية السلوت)، برسالة خاصة + منشن في روم «المناوبة». **10 دقايق** للضغط.
- **الغياب:** أول مرة بالليلة = تنبيه + اسيل تنبّه وتغطي. ثاني مرة = **إنذار رسمي في نظام الالتزام يخصم من العمولة** (نفس الجدول ونفس رابط الاعتراض).
- **المشاكل:** التصعيدات + تذاكر الصيانة اللي تنفتح وقت المناوبة تنحسب على المناوب حتى لو خلصت مناوبته. «استلمت» خلال 10 دقايق (وإلا تنبّه اسيل، بدون إنذار)، «انحلّت» إذا خلّص. التذكرة لين تتقفل. 30 دقيقة بدون تحديث بعد نهاية مناوبته ← اسيل. لو ساعده زميل تبقى المشكلة باسمه والزميل «مساعد».
- **تشغيل مباشر** من أول يوم، مع شبكات الأمان (القسم ٨) وزر إيقاف كامل في الداشبورد.

## 1. Problem

The evening (17:00–24:00) is covered by a rotation of 1–2 hour slots instead of everyone
being on from 12:00 to 24:00. A rotation only works if (a) everyone knows the slots in
advance, (b) the person on duty is provably present, (c) someone else steps in when they
are not, and (d) problems that start in a slot keep a named owner after the slot ends.
Today none of this exists: escalations ping a fixed list (`CLAIM_NAMES`), maintenance
tickets go to the apartment's assignee, and nobody owns "the evening".

Industry name: an **on-call rotation** with **presence checks**, an **escalation policy**
and **incident ownership**.

## 2. Goals / non-goals

Goals
- Auto-generate a fair nightly rotation, publish it a day ahead, allow peer-approved swaps.
- Prove presence every 15 minutes during a slot; act within 10 minutes of silence.
- Stamp an owner on every escalation and maintenance ticket opened 17:00–24:00 and follow
  it until resolved.
- Feed missed checks into the existing accountability system (warnings, appeals, commission).
- One dashboard tab for the owner and اسيل; everything employee-facing lives in Discord.

Non-goals (explicitly out)
- Presence checks 12:00–17:00. Coverage after 24:00 (the existing off-hours reply stays).
- Prayer-time pauses: the 10-minute window is the owner's chosen answer.
- Measuring who replied to guests in Hostaway: Hostaway has no author field on outbound
  messages (see musaed-training-export), so presence is proven by the button, not inferred.
- An employee web page: Discord only (owner choice).
- Any change to who may close a maintenance ticket, or to the existing escalation re-ping loop.

## 3. Architecture

A new package **`oncall/`**, same dependency-injection shape as `schedule/` and `ops/`:

| File | Role |
|---|---|
| `engine.py` | **PURE**, no I/O, TDD-locked: `build_night`, `check_times`, `miss_decision`, `issue_owner`, `stale_decision`, `swap_decision` |
| `db.py` | `oncall_*` tables inside `brain.db` (same connection rules: no WAL, `closing(connect())`) |
| `notify.py` | Arabic message texts + the minute tick (`tick(now)`) that drives publish/lock/checks/ladder |
| `host.py` | `HOST` + `wire({...})` — bot.py injects Discord send/DM/edit callables, so the package never imports bot.py |
| `routes.py` | `/api/oncall/*` (login + `oncall` permission + editor role) |
| `switch.py` | stored ON/OFF switch that beats env (pattern from `ops/switch.py`) |

bot.py changes are limited to: wiring in `start_web_server`, one `oncall_loop`, three small
hooks (escalation posted, maintenance ticket opened/closed, message in a ticket channel),
the persistent check-in / swap / resolve views, one NAV_DEF entry, one dashboard view.

### Reused, not rebuilt
- **Who exists, off days, leave:** `schedule_employees.off_day` + `schedule_absences` via
  `ops.notify.on_leave` / `schedule.db`. No second employee list.
- **Discord ids:** `ops.notify.employees()` (typed ids > env > assignments.json, with the
  `ماذر→مآثر` alias). Unlinked = unreachable = never scheduled, never warned.
- **Warnings, appeals, commission:** `ops_obligations` / `ops_warnings` / appeal pages.

## 4. Data (brain.db)

```
oncall_nights   (date PK, status draft|published|locked, published_at, locked_at,
                 roster_json, note)
oncall_slots    (id PK, date, employee, employee_did, start_min, end_min,
                 source auto|swap|edit, edited_by, UNIQUE(date,start_min))
oncall_swaps    (id PK, date, slot_id, requester, target, kind exchange|takeover,
                 status pending|accepted|declined|expired|cancelled, created_at, decided_at,
                 message_id)
oncall_checks   (id PK, slot_id, employee, due_at, sent_at, dm_ok, channel_ok,
                 answered_at, status pending|answered|late|missed|voided, void_reason,
                 message_id, UNIQUE(slot_id, due_at))
oncall_issues   (id PK, kind escalation|maint, ref UNIQUE, owner, slot_id, opened_at,
                 claimed_at, claimed_by, helper, resolved_at, resolved_by, last_update_at,
                 stale_alerted_night, claim_alerted_at)
oncall_events   (id PK, at, kind, employee, detail)          -- append-only audit
oncall_meta     (key PK, value)                               -- loop heartbeat, last publish
```

Minutes are minutes after 17:00 local Riyadh (0..420), so a slot is `[start_min, end_min)`.

## 5. The rotation engine (`engine.build_night`)

Input: `date`, `roster` (default the five names, editable in the tab), each person's
`working` flag (not their weekly `off_day`, not on recorded leave, Discord linked), and the
last 7 nights' slots.

1. `n` = available people. `n == 0` → night is **uncovered**: published as such and اسيل is
   alerted at 12:00. No checks, no warnings.
2. Lengths: every person gets `7 // n` hours; the `7 % n` remainder hours go one each to
   the people with the **fewest hours in the trailing 7 nights** (ties: fewer long slots,
   then roster order rotated by day-of-year). n=5 → 2,2,1,1,1 · n=4 → 2,2,2,1 ·
   n=3 → 3,2,2 · n=2 → 4,3 · n=1 → 7.
3. Order: the **last slot (ends 24:00)** goes to whoever held it least recently; remaining
   slots are ordered so nobody repeats yesterday's position when avoidable.
4. Deterministic: same inputs → same night (tests rely on this).

TDD invariants: lengths sum to 7 h and are contiguous with no gaps/overlaps; n=5 gives
{2,2,1,1,1}; over a simulated 7-night week with 5 people max−min total hours ≤ 1;
nobody holds the last slot two nights running when n ≥ 2; leave/off-day/unlinked people
never appear.

## 6. A day, minute by minute (Riyadh time)

| When | What `notify.tick` does |
|---|---|
| **12:00** | Build + publish **tomorrow** in «المناوبة»: one message, each slot with «🔁 أبي أبدّل». Unlinked or on-leave roster members listed in red; empty night → alert اسيل. |
| **12:00–15:00 (night day)** | Swaps open for tonight (published yesterday) and tomorrow. |
| **15:00** | Tonight `locked`: pending swaps expire (both told), swap buttons disabled. After this only an editor (admin / اسيل) changes slots, from the tab. |
| **slot − 15 min** | DM: «مناوبتك تبدأ ٧:٠٠ وتخلص ٩:٠٠». |
| **slot start, then every 15 min** | Check: DM with «✋ موجود» + mention in «المناوبة» (one message, edited when answered). Window 10 min. |
| **slot end** | Handover post to the next person: open issues and their owners. |
| **24:00** | Night summary to اسيل (DM + channel): checks answered / missed, warnings, issues still open. |

### Swaps (`engine.swap_decision`)
Any rostered person presses «أبي أبدّل» under someone else's slot. If the requester has a
slot that night → **exchange**; if not → **takeover** (owner becomes free). The slot owner
gets «موافق / لا» by DM. On accept: slots rewritten (`source=swap`), the published message
edited, اسيل informed. Refused when: night locked, requester or target unlinked/on leave,
the slot already has a pending request, requester presses on their own slot. Only the
target's Discord id can answer.

## 7. Presence checks and the miss ladder

- The check button counts only when pressed by the slot owner's Discord id; anyone else
  gets «هذي مو مناوبتك» (ephemeral).
- Answered within 10 min → `answered`. After 10 min → the miss is recorded at the 10-minute
  mark; a later press marks it `late` (still a miss).
- **Delivered** = the DM or the channel mention returned a Discord message id. A check that
  was not delivered is `voided`, never a miss.
- **Bot downtime:** if the loop heartbeat has a gap > 2 min spanning a check's send time or
  deadline, that check is `voided` («البوت كان متوقف»). The employee never pays for a restart.

`engine.miss_decision(misses_tonight)` — per employee per night:
1. **1st miss** → DM the employee («ما ضغطت موجود»), alert **اسيل** (DM + mention): «نوره ما
   ردّت — غطّي المناوبة لين ترجع». No warning.
2. **2nd miss** → `ops.db.ensure_obligation(kind='oc', period_key='OC-YYYY-MM-DD', …)`
   marked `missed`, then **`ops.db.issue_warning`** with reason «غياب عن المناوبة مرتين
   ليلة …». DM carries the existing appeal link; اسيل alerted again. Commission is
   recomputed through the existing path (owner decision: on-call warnings **do** cut
   commission).
3. **3rd+ miss** → اسيل alerted; no second warning (UNIQUE(obligation_id) = one per night).

The principle "the system accuses, humans only forgive" is kept: the warning is issued only
from `oncall.notify` deadline code, never from a route or button. The ops invariant test
(`test_issue_warning_is_called_from_exactly_one_place`) is updated to allow exactly this
second call site and to assert `oncall/routes.py` cannot reach it.

## 8. Issue ownership

`engine.issue_owner(now, slots)` → the slot owner whose `[start,end)` contains `now`, or
None outside 17:00–24:00 (then nothing changes from today's behaviour).

- **Escalation:** hook where the 🚨 card is posted (`post_assistant_card`, bot.py ~15602).
  The card gains «المناوب المسؤول: نوره» + a mention, and a «✅ انحلّت» button. «استلمت» is the
  **existing** Claim button — the hook records `claimed_at/claimed_by`. If someone other
  than the owner claims, the owner stays owner and the claimer is stored as `helper`.
  Not claimed within 10 min → اسيل alerted once (no warning). «انحلّت» may be pressed by
  the owner, the helper, or an admin.
- **Maintenance ticket:** hook in `_maint_open_ticket` (bot.py ~67925). The ticket card gets
  «متابع المناوبة: نوره». The existing apartment assignee is **unchanged**; ownership ends
  when `_tk_close` runs (close rules untouched). A message from the owner in the ticket
  channel counts as an update.
- **Stale rule (`engine.stale_decision`):** after the owner's slot has ended, and while it is
  still 17:00–24:00, no update for 30 min → اسيل alerted, **at most once per issue per night**
  (a ticket waiting days for a plumber must not ping every 30 min). Open issues carry over
  to the next evening's handover and the tab until resolved.

## 9. Safety nets (live from day one, no trial week)

1. No warning for an undelivered check or one spanned by bot downtime (§7).
2. Unlinked employees are never scheduled; shown red at 12:00 with a note to اسيل.
3. **No obligation without a published night:** a night that was not published at 12:00 the
   day before never produces a miss. Deploying in the afternoon means the first real night
   is tomorrow.
4. Buttons verify the presser's Discord id.
5. Master switch in the tab (stored, beats env). OFF = no checks, no alerts, no warnings,
   immediately. Default ON in code (the owner does not edit Railway).
6. Loop guard persisted in `oncall_meta` (the @tasks.loop-runs-on-every-deploy trap): publish
   and lock are idempotent by `oncall_nights.status`; checks by `UNIQUE(slot_id,due_at)`.
7. Deploy etiquette: avoid pushing between 17:00 and 24:00 (a restart voids checks fairly but
   still costs coverage visibility).

## 10. Dashboard tab «المناوبة» (`oncall`)

Visible to admins and اسيل (new NAV_DEF key `oncall`, added to the permissions matrix;
existing non-admin users see it only after the owner ticks it). Sections:
**الحين** (who is on, last answered check, next check, open issues) · **الليلة / بكرة**
(slots; editors can reassign a slot with a required reason → `source=edit`, logged) ·
**المشاكل المفتوحة** (owner, helper, age, status) · **السجل** (misses, voided checks with
reason, warnings with links to /compliance) · **الإعدادات** (roster, supervisor, interval 15,
window 10, master switch). Built with the locked `:root` tokens; JS esprima-parsed.

Discord channel «المناوبة» is created by an admin command `!ouja oncall-setup`, never
automatically (visible to the five, اسيل and admins).

## 11. Testing

- `tests/test_oncall_engine.py` — §5 invariants, check times (2 h slot → 8 checks at
  0,15…105), miss ladder 1→alert 2→warning 3→alert, voided-never-counts, owner lookup at
  slot boundaries (16:59 None, 17:00 first slot, 23:59 last slot, 00:00 None), stale once per
  night, swap refusals.
- `tests/test_oncall_flow.py` — fake host + temp brain.db: publish→swap→lock→checks→miss→
  warning row in `ops_warnings` with `kind='oc'`, idempotent double tick, downtime voiding.
- Updated `tests/test_ops_flow.py` invariant (§7).
- Full CLAUDE.md verification routine; esprima on every DASHBOARD_HTML `<script>`.
- Screenshots of the channel messages (rendered from the real texts) and the tab, sent to
  the owner before any push.

## 12. Assumptions for the owner to confirm in review

1. Weekly «4 clean weeks retires the oldest warning» applies to on-call warnings too, and a
   week containing an on-call warning does **not** count as clean.
2. The stale-issue alert to اسيل fires at most once per issue per night (§8).
3. On a maintenance ticket the on-call owner is a **follow-up owner**; the apartment's
   assigned employee stays as today.
4. Someone not in tonight's rotation may request a **takeover** of a slot (not only a swap).
5. Swaps need no approval from اسيل; she is informed.
