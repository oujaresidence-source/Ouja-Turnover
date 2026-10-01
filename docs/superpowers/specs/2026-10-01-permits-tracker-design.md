# Ouja Permit Tracker «التصاريح» — design (approved)

> Source: Faisal's SUPER PROMPT v2 (2026-10-01), the brainstorming output pre-approved by the owner.
> §§ 1–14 below restate it section by section (condensed — every rule kept, long prose and
> tables shortened; the oracle CSV is verbatim in `tests/fixtures/permits/expected_seed.csv`);
> § 15 (the gate ledger) lives in `permits/GATES.md`.
> The last section, **Decisions made during build**, records every choice the build made on its own
> under the prompt's decision rule (never lose a permit → never double-notify → touch fewer lines →
> follow the wifi/ pattern).

---

## 1. The problem and what success means

Ouja holds many **permits/licences** (تصاريح وتراخيص), each with a start date and an end date. Today
nothing watches them, so a permit can expire unnoticed.

Success:
1. Every permit we hold is visible in one place: a new dashboard tab **«التصاريح» / "Permits"**. It
   shows the end date, the days left, and a status colour.
2. When a permit is **within 10 days of its end date**, or already past it, a **ticket channel opens
   automatically under the maintenance category «صيانه»** in Discord. Exactly one ticket opens per
   permit, carrying every detail we have.
3. A **daily reminder** posts in Discord with the full picture. Each open permit ticket also gets its
   own daily nudge, which escalates as the date gets closer and after it passes.
4. A ticket **cannot be closed** without one of two things:
   - a renewal: the new end date plus proof uploaded in the channel; or
   - a deliberate "won't renew" by an authorised person, with a reason.

   This is what makes "never missed" structural rather than a matter of discipline.
5. Restarts, redeploys, two bot copies overlapping during a deploy, a deleted channel, a full
   category, and the bot being down on the exact day **cannot** cause a missed or duplicated ticket.

**What a "permit" is here:** the seed is 45 Ministry of Tourism **private tourist hospitality facility
permits** (تصريح مرافق الضيافة السياحية الخاصة). There is one per apartment, each valid one year and
issued in the **owner's** name. A renewal therefore usually needs the owner's action (Nafath approval
on the ministry platform), which is why each ticket shows the holder's name and the 30-day heads-up
appears in the digest.

The system stays generic, because other dated permits will be added later (unit tourism licence,
municipality licence, civil defence certificate, compound work/access permits, company documents —
السجل التجاري، رخصة فال، اشتراك الغرفة التجارية — anything else in the seed). Types are **free text
with suggestions**, never a hard enum. The seed decides what exists.

## 2. The seed — `ouja_permits_official.xlsx`

### 2.1 What the file is
- One sheet `تصاريح الوحدات`; row 1 is a merged title (A1:L1); **row 2 is the header**; rows 3–47 are
  **45 permits**; no blank rows, no second sheet.
- Every row: a Ministry of Tourism permit, one per apartment, **in the property owner's name**, valid
  exactly **one year** (365 Gregorian days issue → expiry).
- Seed constants: `permit_type='تصريح مرافق الضيافة السياحية الخاصة'`, `issuer='وزارة السياحة'`,
  `scope='unit'`, `source='seed'`.
- Every value is a string except the serial `م` (a float). **All dates are Hijri `DD/MM/YYYY`**
  (Umm al-Qura, converted with `hijridate`). The header's «(هجري)» is a calendar hint; «الإنتهاء» is
  spelled with إ and header normalisation turns إ into ا.

Header → field mapping (A→M): `م`→`source_ref`+`serial`; `اسم الوحدة`→`unit_text`; `ملف التصريح`→
`doc_name` + **`doc_url`** (the cell's Google Drive hyperlink — all 45 rows); `رقم التصريح`→`permit_no`
(text, never int); `اسم المصرح له`→`holder`; `تاريخ الإصدار (هجري)`→`start_date_raw`→`start_date`;
`تاريخ الإنتهاء (هجري)`→`end_date_raw`→`end_date`; `رقم الهوية`→**`holder_id_last4` only**; `الحي`→
`district`; `الشارع`→`street`; `رقم المبنى`→`building_no`; `رقم الوحدة`→`unit_no`; `نوع العقار`→
`ownership_kind`.

Text cleanup: strip bidi controls (U+200E U+200F U+202A–U+202E U+2066–U+2069), trim, collapse spaces.

**Hyperlink trap:** openpyxl `read_only=True` does NOT load hyperlinks → load `.xlsx` with
`read_only=False, data_only=True` (≤ 5 MB); test all 45 `doc_url`s start with
`https://drive.google.com/`.

### 2.2 The verified expected result (the oracle)
Saved as `tests/fixtures/permits/expected_seed.csv`; `tests/test_permits_seed_real.py` asserts every
row and column (serial, unit_text, permit_no, raw Hijri, Gregorian start/end, district, building_no,
unit_no, ownership_kind, Drive link). It skips only if the (git-ignored) xlsx is absent and fails if
Hijri conversion is unavailable on Python ≥ 3.10.

Timing (measured 2026-10-01): **F2 (serial 13, permit 50035533) expires 2026-10-12 (01/05/1448)** and
enters the 10-day window on **2026-10-02** — the expected first ticket at go-live. Next wave: Malqa 1
and C08 (2026-11-23), A5 (2026-11-24), C2 (2026-11-30), then 9 in December. Latest expiry: 6B,
2027-08-04.

### 2.3 Privacy — the national ID column (non-negotiable)
- **Store only the last 4 digits** (`holder_id_last4`). The full number never enters SQLite, JSON,
  logs, Discord, the dashboard, fixtures, commit messages or this spec.
- **The raw xlsx is never committed**: `permits/seed/source/` is in `.gitignore` (committed first);
  `git check-ignore` proves it.
- `permits/seed/permits_seed.normalized.json` (committed) holds holder names, last-4 and Drive links,
  never full IDs.
- **Gate G13** (`permits/tools_privacy_scan.py`) fails on any `\b[12][0-9]{9}\b` in a file the branch
  adds/changes, and in **added** bot.py lines.
- Discord shows the holder **name** only; the dashboard drawer shows `•••• 1234` to admin/ops only.
- The generic importer follows the same rule for any ID-looking header (هوية / سجل مدني / إقامة /
  national id / iqama / id number).

### 2.4 Known data problems (import all; flag, never "fix" by guessing)
Each becomes a `review_issues` entry `{code, text_ar}` → amber chip «تحتاج مراجعة»; **review issues
never stop tickets or reminders**.

| Rows | Problem | code |
|---|---|---|
| 19 `101a` + 44 `201b` | same permit number 50037629, same dates, same holder, both unit 201 | `dup_permit_no` |
| 1 `101b` | name 101b but unit 202 / file ٢٠٢b.pdf | `unit_mismatch` |
| 43 `202B` | file 201A.pdf, unit 201, building 7569 | `unit_mismatch` |
| 19 `101a` | name 101a but unit 201 | `unit_mismatch` |

`dup_permit_no` is detected generically; the three `unit_mismatch` rows are a hard-coded reviewed list
in `build_seed.py`. **No UNIQUE index on `permit_no`.** An admin clears an issue in the drawer with a
note (logged).

### 2.5 Linking each permit to a Hostaway apartment
Resolve `unit_text` against the **live** listings store at seed time and on every daily batch for
still-unlinked rows. Normalise (lowercase, strip `Ouja |`/`عوجا`, أإآ→ا ة→ه ى→ي, `-`/`_`/`ـ`/spaces →
one space; also the ASCII slug). Order: exact normalised → exact slug → the hint (only if it resolves
to exactly one live listing) → a unique contains-match. **Never pick between two candidates.** No
unique match → `listing_id = NULL` + chip «غير مربوطة بشقة». A drawer «اربطها بشقة» dropdown sets a
manual link the auto-linker never overwrites. Hints come from the stale guide slugs
(`supabase_export_listings.csv`), high/medium confidence only.

### 2.6 Seed loading
`build_seed.py` (xlsx → normalized JSON, re-runnable); `seed.py: seed_if_empty()` loads it on boot only
when `permits_permits` is empty, then auto-links. Commit the JSON + script, never the xlsx. The import
screen accepts future CSV/XLSX/JSON through the same importer (Arabic/English header synonyms; dates in
Gregorian, Hijri, Arabic-Indic digits or Excel serials, day-first with ambiguity flagged; unknown
columns → `extra_json`; unparseable end date → `needs_data`, never dropped). Header row = the row (of
the first 10) with the most synonym hits. «من مشاريع التشغيل» reads `onb_projects.license_no /
license_expiry` **read-only**; existing numbers are marked «موجود»; nothing is auto-imported.

## 3. Read before writing
`wifi/` is the template (host/db/engine/routes, `_safe` wrappers, `register(app)`). Reuse `brain.db`
(`journal_mode=DELETE`, never WAL), `permits_*` tables, `PRAGMA table_info`-guarded `_migrate`. Import
guard next to wifi; `_permits.wire({...})` + `register_routes(app)` next to wifi in
`start_web_server`; the package never imports bot. Role rules: write + read `("/api/permits/",
"permits")`; edit = admin/ops (`can_edit_permits`). Handlers use `HOST.web_thread` — **never
`asyncio.to_thread`**. Nav comes from **`NAV_DEF`** (item `{"id":"permits","ic":"tickets","tk":
"permits","badge":"permits"}` right after `wifi` in `cat_ops`, labels in both languages); `go()` gets
`if(id==='permits') loadPermits();`; a `<section class="view" id="view_permits">`; the badge reads
`D.permits.counts.alert`. The tab's JS lives in `permits/static/permits_tab.js` (public static, `?v=
<mtime>`), DASHBOARD_HTML holds only the section, a ≤15-line zero-backslash stub and the badge lines.
Discord: `_tk_category(guild,"maint")`, `_tk_make_channel` (spill «صيانه ٢…٨»), `_tk_lock_channel`,
`_maint_has_proof` (fails open), `_maint_can_close`, `maint_assignee_for`, `ensure_channel`,
`_send_long_to_channel`. Topic prefix **`ouja-permit:`** (never `ouja-ticket:` / `ouja-watchman:`).
Loop: the `directpay_nudge_loop` pattern (persisted latch), never `@tasks.loop(time=...)`, started
staggered in `on_ready`, in `_loop_guard`, `before_loop → wait_until_ready`; `bot.add_view(
PermitTicketView())`. Slash command names are ASCII.

## 4. Files (approved scope)
New: `permits/{__init__,host,db,dates,engine,importer,service,port,routes}.py`,
`permits/static/permits_tab.js`, `permits/seed/{build_seed,seed}.py`,
`permits/seed/permits_seed.normalized.json`, `permits/GATES.md`, `tests/permits_fakes.py`,
`tests/test_permits_{dates,engine,importer,service,routes_gating,dashboard,seed_real}.py`,
`tests/fixtures/permits/expected_seed.csv`, this spec, the plan. Edited: `bot.py` (glue only, under
`# ==== PERMITS «التصاريح» ====`), `requirements.txt` (`hijridate~=2.6`), `CLAUDE.md` (section + trap
2 fix), `.gitignore` (`permits/seed/source/`).

## 5. Data model
Tables `permits_permits` (every column of the prompt's DDL), `permits_tickets` with
`idx_permits_one_live_ticket ON permits_tickets(permit_id) WHERE state IN ('opening','open')`,
`permits_outbox` with a UNIQUE `ref`, `permits_events` (append-only), `permits_settings` (`mode` default
`dry`, `mode_changed_by/at`, `digest_date`). Invariants: a renewal is ONE transaction (old → renewed +
replaced_by_id; new row replaces_id + source='renewal'; live ticket → closed/renewed; outbox
close_ticket); an end-date correction needs a reason and closes the live ticket as `corrected` when it
leaves the window; nothing is DELETEd.

## 6. Engine and service rules
Bands (one function): expired (<0) · urgent (0–3) · due (4…lead) · upcoming (lead…30) · ok (>30) ·
unknown (NULL / needs_data); `alert = expired+urgent+due+unknown`. Live = `status='active'`.
`plan()`: open a ticket at `days_left <= lead` (catch-up) with no live ticket; unknown dates never
auto-open; daily in-ticket reminder at/after `PERMITS_DAILY_HOUR`; the digest once per Riyadh day with
the latch persisted only after a successful send. Opening is crash-safe: ticket row `opening` + outbox
`open:t<id>` in one transaction; atomic claim; success → `open`; failure → `failed` + backoff
(1, 5, 15, 60, then hourly) + shown in «مشاكل النظام»; stale `opening` (>15 min) → adopt by topic or
retry, never a second channel. Channel `تصريح-{tid:03d}-{slug}`, topic `ouja-permit: pid:{pid}
tid:{tid} end:{end}`. Lost channel → `lost` + a replacement whose card says «التذكرة السابقة #{old}
انحذفت — هذي بديلتها»; a failed check is never a deletion. Three closing doors only: renewed (new end >
old and ≥ today, proof), cancelled (`_maint_can_close` / dashboard admin, reason 5–400), corrected.
Escalation: due → responsible; urgent → + `PERMITS_PING_ROLE_ID`; expired → + `PERMITS_ESCALATE_IDS`.
A claim never silences. No snooze. Quiet hours: new tickets open in `[9, 22)`; expired permits ignore
them only on the first detection after go-live. Dry vs live as above; going live needs the typed word
«تشغيل»; `PERMITS_FORCE_DRY=1` overrides. Loop every `PERMITS_TICK_MIN` (5): reconcile → plan →
enqueue → drain, each step isolated; guild None → Discord steps skipped; `last_tick_at` heartbeat
(dashboard red after 30 min).

## 7. What Discord shows
The pinned card (title `📄 تصريح #{tid:03d} — {type} · {unit}`; fields النوع، الرقم، الشقة/المبنى، جهة
الإصدار، باسم (name only)، العنوان، التصريح الحالي (Drive)، تحتاج مراجعة، البداية، النهاية (both calendars)،
المتبقي، التكلفة، طريقة التجديد، ملاحظات، extra_json fields (≤25 total, overflow into «معلومات
إضافية»)، المسؤول، الداشبورد; footer `permit:{pid} · ticket:{tid}`; content = mention + «— تذكرة تجديد
تصريح», prefixed `🚨 **عاجل** ·` when urgent/expired). `PermitTicketView` (persistent, `permit_*` ids):
✋ أستلمها · ✅ تم التجديد (proof first, modal, confirmation in words, re-check at press) · 🚫 لن يُجدَّد
(`_maint_can_close` only, reason modal) · 📋 التفاصيل (ephemeral + last 10 events). The daily digest
at 13:00 in `تنبيهات-التصاريح` under «صيانه» (blocks 🔴 / 🟠 / 🟡 / ⚪ / ⚠️ مشاكل النظام / ✅ تجدّد أمس;
an all-clear one-liner when nothing needs attention; ≤2000 chars per message; mentions only for the
responsible people of expired/urgent items). `/permits` (ASCII) = an ephemeral read-only digest.

## 8. The dashboard tab
Mode banner + switch (admin), «آخر فحص» heartbeat, KPI tiles that filter, a 12-month expiry strip,
the table (sorted unknown → expired → by days left; pill · type · number · unit chips «غير مربوطة» /
«الشقة غير نشطة» · issuer · start · end (+Hijri) · left · ticket link / «تنفتح بعد n يوم» / «وضع
التجربة» · responsible), filters, phone cards at 380 px, a drawer with every field, Hijri as written,
Drive link, `•••• 1234` for admin/ops, review issues + «تمت المراجعة», «اربطها بشقة», document, chain,
events, and the actions تعديل / تجديد / لن يُجدَّد / رفع مستند. Add (live date preview in words + Hijri,
warn >5 years or end < start), Import (preview → «استيراد {n}», duplicates skipped unless «حدّث
الموجود», utf-8-sig/utf-8/cp1256, 5 MB), Export (CSV utf-8-sig, both calendars). Viewers see no action
buttons; the server re-checks every write.

## 9. HTTP API
`GET /permits/static/permits_tab.js` (public) · `GET /api/permits/{summary,list,item,months,
preview-live,doc,export.csv}` · `POST /api/permits/{create,update,renew,cancel(admin),doc-upload,
import/preview,import/commit,mode(admin),link,review-clear(admin)}`. JSON `{"ok":true,...}` /
`{"ok":false,"error_ar","error_en"}`. Discord-affecting writes only enqueue; the UI says «بيتحدّث
ديسكورد خلال دقائق».

## 10. Env vars
`PERMITS_ENABLED`(1) · `PERMITS_LEAD_DAYS`(10) · `PERMITS_HEADSUP_DAYS`(30) · `PERMITS_DAILY_HOUR`(13) ·
`PERMITS_OPEN_FROM`/`TO`(9/22) · `PERMITS_TICK_MIN`(5) · `PERMITS_DIGEST_CHANNEL`(تنبيهات-التصاريح) ·
`PERMITS_PING_ROLE_ID`(0) · `PERMITS_ESCALATE_IDS`(= MAINT_CLOSE_IDS) · `PERMITS_FORCE_DRY`(0). Read at
call time; garbled ints fall back to the defaults and are logged.

## 11. Failure modes (each a test or a gate)
F1 catch-up · F2 restart/redeploy latches · F3 two copies → one channel · F4 crash mid-open → adopt ·
F5 50-channel cap → spill · F6 Discord error → failed + backoff + digest · F7 deleted channel →
replacement · F8 can't check ≠ deleted · F9 unreadable date → needs_data · F10 date formats + ambiguity
· F11 duplicate number → both tracked + flagged · F12 no other close path · F13 renewal date ≤ old /
past refused · F14 claimed-then-forgotten still nudged · F15 wrong seed → dry default · F16 dead loop →
`_loop_guard` + red heartbeat · F17 Riyadh time at 23:59 / 00:01 · F18 size limits with 300 permits ·
F19 cleanup jobs ignore permit rooms · F20 inactive unit chip · F21 path traversal → uuid paths, served
by id · F22 hijridate missing → flagged, tests skip · F23 ID leakage → last-4 + gate · F24 openpyxl
hyperlinks → read_only=False · F25 bidi stripped · F26 unique-or-nothing linking.

## 12. Non-goals
No snooze/mute; no push into `/api/tickets`; no WhatsApp/SMS/email; no edits to `onboarding/`, `mot/`,
`wifi/` or the maintenance-ticket code (reuse by calling only); no deleting closed permit channels; no
Hostaway changes.

## 13. Pre-answered questions
Category «صيانه» via `_tk_category`; within 10 days (`≤`) with catch-up and per-permit `lead_days`;
reminders 13:00 Riyadh, every day incl. weekends/holidays; responsible = permit field →
`maint_assignee_for` → default; nobody closes directly; end date inclusive (0 = «ينتهي اليوم»);
unexpected columns → `extra_json`; unreadable date → `needs_data`; unmatched units → «غير مربوطة»;
store Gregorian, show both; go-live opens all expired permits in the first tick (the confirm states
the count); one live ticket per permit row (a renewal is a new row); tab after «اشتراكات النت»; admins
see it immediately, others once ticked in الصلاحيات; JS in a static file; `brain.db`; push only when
`PUSH_AFTER_GATES = YES`; baseline the two pre-existing `test_ops_capture.TestBackfill` failures;
esprima/pyflakes are dev tools; Umm al-Qura via `hijridate` with the Hijri shown as written; both
19/44 kept; last-4 is enough; never commit the xlsx; blank cost/responsible/notes with the type default
renew note «التجديد من منصة وزارة السياحة — يحتاج موافقة المالك عبر نفاذ».

## 14. Tests to write first
`test_permits_dates.py`, `test_permits_engine.py`, `test_permits_importer.py`,
`test_permits_service.py` (FakePort + temp brain.db, incl. `RaceTest`, `DryDefaultTest`),
`test_permits_seed_real.py`, `test_permits_routes_gating.py`, `test_permits_dashboard.py` — every case
listed in the prompt's § 14.

---

## Decisions made during build

1. **Worktree, not the parked checkout.** Built on branch `feat/permits` in `../ouja-wt-permits` off
   `origin/main` (the main checkout is parked on `feat/musaed-v2`; switching it would revert live code
   for parallel sessions).
2. **Hijri locally:** `hijridate` 2.6 needs Python ≥ 3.10. Local Python is 3.9, so 2.5.0 (same Umm
   al-Qura table) was installed `--user` for dev, and a 3.13 venv with 2.6 runs the pure tests (gate
   G3b). Both reproduce the oracle exactly. `requirements.txt` pins `~=2.6` for Railway (3.13).
3. **`ensure_card` added to the port contract.** If Discord creates the channel but posting the card
   fails, adoption-by-topic would leave a room with no card and no buttons. `ensure_card` returns the
   existing card (matched by footer) or posts it. Rule 1 (never lose a permit).
4. **Outbox `next_at` column** (not in the prompt's DDL) stores the backoff time; added in the CREATE
   and via the `_migrate` table for future DBs.
5. **No reminder on the opening day.** A new ticket's `last_reminder_date` is set to the day it opens —
   the card itself is that day's nudge. Rule 2 (never double-notify).
6. **A lost-channel replacement respects quiet hours** (it opens in the same tick when inside 09–22,
   otherwise at 09:00). The prompt forbids special-casing quiet hours beyond the go-live sweep.
7. **All-clear digest + renewals.** When nothing needs attention the digest is the one all-clear line;
   if something was renewed yesterday, the «✅ تجدّد أمس» lines follow it (good news is not dropped).
8. **«تشغيل» with surrounding spaces is accepted** (trimmed) — the same as `ops/switch.py`.
9. **Channel slug keeps Arabic letters when there is no ASCII** (e.g. «العارض ـ ابو ماجد»), otherwise it
   is `channel_name()`-style ASCII with `ouja-` stripped; ≤ 40 chars; `permit` as the last fallback.
10. **Unit hints:** only the high/medium-confidence hints are in `engine.SEED_HINTS`; the "low" ones
    (العارض-C2, TWN 13, 22 هاجر, D2 صاد) are left to exact/slug/contains matching and the manual dropdown.
11. **Extra endpoint `GET /api/permits/parse-date`** (read, same `permits` rule) powers the live «date
    in words + Hijri as you type» preview — the browser cannot convert Hijri reliably on its own.
12. **Go-live and review-clear use in-drawer forms**, not `window.prompt`: the go-live drawer lists the
    exact tickets that will open and asks for the typed word.
13. **Short type label in the table** (`TYPE_DEFAULTS[...]["short"]` = «تصريح ضيافة سياحية»), the full
    type in the tooltip, drawer and Discord card; issuer + start columns hide below 1180 px.
14. **The table uses its own `.pm-num` class** — the dashboard's global `.num` makes cells
    `inline-block`, which broke the column alignment (found in the browser, not by a parse).
15. **Free-text ID masking.** Besides ID-named columns (last 4 only), any national-ID-shaped number in
    any other imported cell is stored as `••••1234`.
16. **Opening isolates (U+2066–2068) become a space** before the bidi strip, so «F1⁨الأستاذ» style
    names stay two words (serial 3's own cell has no space — it is stored as typed).
17. **Discord-button DB calls are synchronous** (sub-millisecond SQLite) so the 3-second interaction
    deadline never waits on a busy thread pool; the loop uses `asyncio.to_thread` as the prompt says.
18. **Smoke seam (G11):** `permits/tools_smoke.py` imports bot.py (no Discord login happens at import),
    builds an aiohttp app with bot.py's real `_role_enforce_mw`, wires the package with bot.py's real
    `_permits_caps()`, seeds a throwaway brain.db and makes real HTTP calls on a local port.
19. **Privacy scan base:** G13 scans everything the branch changes **relative to `origin/main`**
    (committed or not), so it still means something after the commit; bot.py contributes added lines
    only.
20. **Boot badge fetch:** `permitsBadgeRefresh()` runs from `loadAll()` at most every 10 minutes,
    non-blocking, errors swallowed, only when the user can read the tab.
21. **Not pushed.** `PUSH_AFTER_GATES = NO`.

Fixes from the independent code review (each with a test in `test_permits_service.ReviewFixesTest`,
`StaleDayTest`, `LateOpenTest` or `test_permits_importer.TestReviewFixes`):

22. **An unreadable date never closes a ticket.** An «حدّث الموجود» import whose new date is
    unreadable keeps the old readable date; clearing the end date while a ticket is live is refused;
    `corrected` closes only when a READABLE new date is outside the window.
23. **Escalation fallback is real:** `PERMITS_ESCALATE_IDS` empty → `HOST.escalate_default`
    (bot.py's `_maint_close_ids`), so an expired permit never escalates to nobody.
24. **Digest channel survives a full «صيانه»:** found by name server-wide, created with
    `_make_channel_spill`; the digest posts part by part and remembers how many parts went out, so a
    retry never re-posts (or re-pings) the first part.
25. **«مشاكل النظام» lists every failing post** (open, reminder, close, digest) — in the digest and in
    a red line on the tab.
26. **Live heartbeat = Discord last reached** (`last_discord_ok_at`, written after a ready live pass),
    so a wrong GUILD_ID cannot hide behind a healthy-looking «آخر فحص».
27. **Stale-day posts are dropped:** a reminder/digest that failed all of yesterday is not posted
    today next to today's own. **A ticket closed while its room was being created stays closed** and
    the late room is locked/renamed.
28. **Reconcile no longer resets a claim by the TICKET's age** (only `_reset_stale_claims`, by the
    claim's age) and one un-checkable channel no longer stops the lost-channel scan for the others.
29. **«✅ تم التجديد»** uses a time-boxed one-page proof check (fails open) so the modal always beats
    Discord's 3-second deadline; the confirm step re-checks with the full scan. Button WRITES (claim,
    renew, cancel, details) now run in a thread after the interaction is answered.
30. **Permit numbers are never masked** (a 10-digit CR number is a number, not an ID); a manual unit
    link survives an update import; the drawer links `doc_url` only when it is `https://` (also
    enforced on create/edit); event and claim times are shown in Riyadh time.
