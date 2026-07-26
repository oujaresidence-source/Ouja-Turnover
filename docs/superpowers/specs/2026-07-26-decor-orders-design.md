# طلبات تنسيق الحفلات — Decoration Orders (design)

**Date:** 2026-07-26 · **Status:** awaiting owner approval — NOTHING built yet
**Owner answers on file:** plan first · Discord role `DEC` · owner fills the unit-features
sheet by hand · orders live in BOTH a Discord **thread** and a dashboard tab.

> **OWNER RULE — 2026-07-26, absolute.** A guest tapping «أنا مهتم» must NOT create a
> ticket, a thread, a task, or an assignment, and must NOT notify or assign anyone.
> It is a silent interest signal to the DEC supervisor and nothing else. **Only the
> supervisor opens the request.** Everything downstream — thread, deadlines, cake
> sub-task, escalation — begins at the supervisor's action, never at the guest's tap.

---

## PART 1 — In plain words (for the owner)

### What exists today
A guest opens `oujares.com/guide/<their-unit>`, taps «أنا مهتم» on one of the five
decoration packages, and WhatsApp opens with a pre-written message. That is all that
happens. Nobody is told, nothing is written down, no deadline exists. If the concierge
misses that WhatsApp message, the guest is simply never answered — and we would never know.

### What this builds
Two separate things, and the difference between them is the whole point.

**اهتمام — an interest.** The same button quietly tells the bot which unit and which package.
That is *all* it does. No ticket, no thread, no task, no deadline, nobody assigned, nobody
notified except the DEC supervisor seeing a new line in a list. A guest tapping a button —
by mistake, out of curiosity, five times in a row — can never put work on anyone's plate.

**طلب — a request.** The supervisor looks at the interest and decides. When they open it,
*then* it becomes real: a thread in Discord, a row in your dashboard tab, a deadline, a cake
job if the package has one, and warnings if it runs late. From that moment it cannot be
forgotten — but it only ever exists because a human chose to create it.

### The life of one request

| Stage | Arabic | What it means |
|---|---|---|
| 0 | اهتمام | The guest tapped the button. **Nothing opened. Nobody assigned.** Only DEC sees it. |
| 1 | فتح المشرف الطلب | A DEC supervisor decided this is real. Everything below starts here. |
| 2 | تنبيه: الشقة ما تسمح | The apartment can't do part of this package. **A warning, not a wall** — the supervisor can override, and the order then carries the warning with it forever. |
| 3 | بانتظار معلومات الضيف | We need the phrases / occasion / cake flavour before anyone can work. |
| 4 | جاهز للإرسال | Everything we need is in hand, and the final price is set. |
| 5 | تم الإرسال للمنسّق | Sent to whoever is doing the setup. |
| 6 | تم التنفيذ | Done. |
| — | ملغي | Cancelled at any point, with a reason. |
| — | تجاهل | The supervisor dismissed the interest. It never became a request. |

### The four rules you asked for

**1. The apartment must be able to do it — and if it can't, we say so out loud.**
Diamond needs a pool. Signature Silver needs a jacuzzi. Silver accepts a jacuzzi *or* a
bathtub. If the apartment doesn't have it, the supervisor is stopped and told exactly which
one is missing — instead of us discovering it on the night, in front of the guest. If we
simply don't know about that apartment yet, they are stopped the same way. Silence is never
treated as a yes.

**But the supervisor can override it**, and there are two different overrides, because they
mean two different things:

- **«لا، الشقة فيها مسبح — القائمة غلط»** — our records were wrong. The list is corrected on
  the spot, the order proceeds completely normally, and every future order for that apartment
  is right. Nothing is stamped, because nothing is missing.
- **«أدري ما فيها مسبح — كمّل»** — the apartment really doesn't have it and we're doing the
  order anyway. The order is created, **and it is stamped**. The stamp says, in plain words:
  > ⚠️ الباقة الماسية فيها تنسيق المسبح، وهذي الشقة ما فيها مسبح.
  > البنود المتأثرة: «تنسيق غرفة النوم والمدخل والحمام والمسبح» · «تنسيق طاولة الطعام والمسبح».
  > تجاوزه: [اسم المشرف] — [التاريخ والوقت].

That stamp is not a note somewhere. It appears **at the top of the Discord thread, on the
dashboard row, and inside the message sent to whoever does the setup** — so the person
arriving with balloons already knows there's no pool, instead of standing in the apartment
working it out. The bot also names the exact lines of the package that are affected, so the
supervisor can decide what replaces them and what the guest is told — and the final price
can be set accordingly, since the guest isn't receiving the whole package.

Every override records **who** did it and **when**. Nobody can push a package through
silently.

**2. The cake is its own job.** Every package except Bronze includes a cake. A cake comes
from an outside bakery and needs 24 hours. So it gets its **own** deadline — one day before
the decoration deadline — its own line in the thread, and its own late-warning. A late cake
and a late decoration are two different failures and will be reported as two different
failures.

**3. Nothing goes out half-finished.** Each package lists what we must get from the guest
(the phrases, the occasion, the cake writing, the letters for the bed…). The request cannot
be sent to the setup person while any of those is still empty. Instead there is a button
that writes a WhatsApp message asking the guest for **exactly** the missing items by name —
not a vague "we need some details."

**4. Two different prices.** The 1,450 / 998 / 799 / 670 / 598 in the guide are «تبدأ من»
prices. They are advertising, not revenue. The supervisor types the **real** agreed price on
each request, and only that number is ever counted as money.

### What I need from you before it can go live
1. **The apartment sheet** — attached, 64 apartments, three columns to tick (pool / jacuzzi /
   bathtub). Until an apartment is ticked, Diamond and Silver on it will stop and ask the
   supervisor every single time. The system still works without the sheet — it just nags. Fill
   it once and the nagging stops for the apartments that genuinely have the feature.
2. **Which Discord channel** the threads should hang under (I suggest a new
   `#تنسيق-الحفلات`, one channel, unlimited threads inside it).
3. **Confirm the deadline rule below** — this is my assumption, and it's the one thing most
   likely to be wrong.

### My assumption about deadlines (please correct me)
> The decoration must be finished by the guest's **check-in time** (3:00 PM Riyadh unless
> Hostaway says otherwise), **unless** the supervisor sets a specific event time — a birthday
> at 9 PM on the second night, for example — in which case that time wins.
> Work must *start* earlier than the deadline by the package's own setup time (Diamond 150
> minutes, Silver 100, Bronze 60 …), and the cake deadline is 24 hours before all of it.

---

## PART 2 — Technical annex

### New package `decor/` (never `import bot`; wired like `guide/` and `schedule/`)

| File | Responsibility |
|---|---|
| `packs.py` | Load + validate `decor_packs.json`. Reads `$STATE_DIR/decor_packs.json` first, falls back to the repo seed — so the owner edits packs on Railway with no redeploy (what the file's own `_note` promises). |
| `engine.py` | **Pure, no I/O.** `capability_check`, `missing_inputs`, `can_dispatch`, `cake_task_for`, `deadlines_for`. Single source of truth, TDD-locked like `schedule/engine.py`. |
| `db.py` | `decor_leads`, `decor_orders`, `decor_cake_tasks`, `decor_unit_features` inside the existing `brain.db` (NO WAL, journal DELETE, `closing(connect())` — the proven rules). **`decor_leads` and `decor_orders` are deliberately separate tables**, so a lead cannot accidentally acquire an assignee, a deadline, or a thread by someone forgetting a status check. |
| `routes.py` | `POST /api/decor/inquire` (**public**, like the guide itself) — writes a `decor_leads` row and returns. It has **no code path** that creates an order, a thread, a task, a cake job, or an assignment. Supervisor endpoints (`/open`, `/dismiss`, …) sit behind `_safe` + a `can_edit_decor` role check (`DECOR_SUPERVISOR_ROLE=DEC`), and `open` is the **only** function in the package that constructs an order. |
| `discord_ops.py` | Thread creation + late-warnings, called from `open` onwards only. `DECOR_DRYRUN=1` on first deploy — computes and logs, posts nothing. |

### Capability gate
- `capability_check` returns one of three verdicts, never a bare boolean: `ok`,
  `missing` (unit known, feature absent), `unknown` (unit not in the features table).
- Runs **twice**: advisory on the lead, so the supervisor sees «هذي الشقة ما فيها مسبح»
  before deciding. Enforced on `open` — which refuses **unless** it is called with an explicit
  override argument. Default-deny, opt-in override; there is no path where a `missing` verdict
  is silently ignored.
- Two override kinds, stored distinctly because they mean different things:
  `correction` (our record was wrong → writes the feature into `decor_unit_features`, so it is
  answered once and for all, order proceeds clean) and `accept_gap` (feature genuinely absent
  → order proceeds **stamped**). Both record `overridden_by` + `overridden_at` + a reason.
- The **stamp** is `engine.capability_stamp(pack, missing_features)` — one pure function, so
  the Discord thread header, the dashboard row, and the vendor dispatch message all render the
  identical Arabic text and cannot drift apart.
- `affected_checklist_items`: each feature maps to its Arabic keywords (`pool` → مسبح,
  `jacuzzi` → جاكوزي, `bathtub` → بانيو/البانيو) and the pack's own `checklist` lines are
  scanned for them — that is how the Diamond stamp names «تنسيق غرفة النوم والمدخل والحمام
  والمسبح» specifically. It is a keyword match over data the owner controls, so it is
  presented to the supervisor as a **pre-ticked suggestion they can adjust**, never as the
  final word. A pack whose wording changes cannot break anything: worst case the list comes
  back empty and the stamp still names the missing feature.
- Feature tokens come straight from `requires_unit_features`. `jacuzzi_or_bathtub` is parsed
  on the `_or_` separator → satisfied if the unit has **either**.
- Keyed by **guide slug** (`h8-vlg`, `c2-nfl`), because the slug is what the guide page knows
  and therefore the only identifier the button can send. The sheet the owner fills carries
  slug + human name side by side.

### Guest-input gate
`requires_guest_input` is read per pack; every `key` must hold a non-empty value before
`can_dispatch` returns true.

**Interaction with an `accept_gap` override — important.** Signature Silver requires
`jacuzzi_text` («عبارة ترحيبية أو أسماء للجاكوزي»). On a unit with no jacuzzi that was pushed
through anyway, that input can never be answered — and the order would sit in
«بانتظار معلومات الضيف» forever, waiting for something nobody can give it. So on `accept_gap`,
inputs tied to a missing feature are marked **«ما ينطبق»** by the same feature→keyword map,
shown struck through rather than hidden, and excluded from the dispatch gate. Without this the
override rule would quietly deadlock the guest-input rule. `can_dispatch` returns the **list of missing keys with their
Arabic labels**, which is what both the block message and the WhatsApp-ask button render
from — one source, so they can never disagree.

### Cake
Created only when `includes_cake` is true (Bronze creates none — asserted in tests).
`cake_deadline = decor_deadline - packs['cake']['lead_hours']` (24h, read from JSON, not
hard-coded). Own row, own state, own escalation path.

### Money
`price_from_sar` is read-only from the JSON and is never summed as revenue.
`final_price_sar` + `vendor_cost_sar` are per-order, supervisor-entered; margin =
final − vendor cost. Feeding this into the ERP expense pipeline is **phase 3, not now**.

### Intake endpoint hardening
The guide page is public, so `/api/decor/inquire` is unauthenticated by necessity:
per-slug rate limit, a dedupe window so a double-tap makes one order, strict slug/pack-id
validation against the loaded packs, and a hard cap on request body size.

### Edits to existing files (deliberately tiny)
- `guide/templates/guide.html` — add `data-pack-id` to the five **events** buttons
  (lines 740, 764, 788, 812, 836) and ~15 lines of JS. Chauffeur (872/892/912) and barbering
  (970) share the `wa-link` class and are **untouched**, because the POST only fires when
  `data-pack-id` is present. The POST uses `keepalive` and a `try/catch` so it can neither
  delay nor break the WhatsApp link: if the bot is down the guest experience is identical to
  today's. This file is served raw, so the `DASHBOARD_HTML` backslash trap does not apply.
- `bot.py` — ~6 lines in `start_web_server` (`decor.wire({...})` + `register_routes(app)`),
  matching the guide/schedule pattern. Nothing else.

### Tests (`tests/test_decor_engine.py`) — the four required, plus
1. Diamond on a unit with no pool → refused, and the refusal names `pool`.
1b. The same order with `accept_gap` → **created**, and carries a stamp naming the pool and
   the two Diamond checklist lines that mention المسبح. The stamp text is byte-identical in
   the thread header, the dashboard row, and the vendor message (one function, asserted three
   times).
1c. The same order with `correction` → created **clean, no stamp**, and the unit's features
   now record the pool, so the next Diamond on that unit doesn't ask again.
1d. An override without a named supervisor or without a reason is refused.
2. Dispatch refused while any required input is empty; allowed once all are filled.
3. Cake deadline is exactly 24h before the decoration deadline.
4. A Bronze order creates no cake sub-task.
5. `jacuzzi_or_bathtub` satisfied by either, blocked by neither.
6. Unknown unit blocks; blocks *differently* from a known-but-missing unit.
7. `price_from_sar` never appears in the revenue figure.
8. **The owner rule, locked in tests:** an inquiry produces a lead and *only* a lead — zero
   orders, zero threads, zero cake tasks, zero assignments, zero notifications to anyone but
   DEC. Ten rapid taps still produce no work. Asserted by counting rows in every other table
   before and after, so any future refactor that quietly re-wires intake fails the suite.
9. A dismissed lead can never later turn into an order.

### Build order (each stage separately reversible)
1. `packs.py` + `engine.py` + tests. **Zero live impact** — nothing calls it yet.
2. `db.py` + `routes.py` + the guide button — **leads only**. The supervisor sees interests
   arriving; nothing can be opened yet, so nothing can go wrong on the ops floor.
3. The supervisor's «افتح الطلب» action, dashboard tab, threads live, late-warnings.
4. (Later) margin → ERP expense capture.
