# «تسليم الرموز» Revision 2: Cards in the Turnover Room + One Button Sends the Code. Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Move codegate's card out of the «تسليم-الرموز» channel and into the apartment's turnover room. When an apartment has no turnover room, open a code-only room in the Turnovers category. Keep the turnover room open until the code is sent. Let one staff-pressed button send the door code itself. Show on the card whether the guest wrote «أوافق».

**Architecture:** Keep the package shape: pure `engine.py`, `db.py`, `host.py`, `flow.py`, and the bot.py bridge. All new Discord and Hostaway side effects stay behind new HOST capabilities, so the flow stays testable with fakes. bot.py gains one dedicated code sender, which honours the kill switch and dedupe and never logs the body. It also gains a guard at the three automatic turnover-room delete sites.

**Tech Stack:** Python 3, discord.py ≥ 2.4, brain.db (no WAL), unittest.

**Spec:** `docs/superpowers/specs/2026-10-21-house-rules-code-release-design.md`. §9 "Revision 2" is binding and overrides §4.2 wherever they conflict.

**Starting point:** branch `feat/agree-gate` at `8fa9ddd` (worktree `/Users/faisalouja/ouja-wt-agree`). Revision 1 (codegate package, soak switch, go-live pre-check) is built and reviewed.

## Global Constraints

- Work only in `/Users/faisalouja/ouja-wt-agree`. Never push. Never touch `/Users/faisalouja/Ouja-Turnover`.
- **Only one path may send a door code: a staff press of `cg_send`, after the confirm step, on a live gated unit.** The outbound firewall (`outbound_firewall`, `_FW_CODE_CTX`, `send_guest_message`) is NOT modified. Musaed and every other sender keep the block.
- The code sender honours `ASSISTANT_SEND_KILL` and uses a persisted dedupe claim (`_once_claim`). It sends `communicationType` `"email"`, like every proactive send. It NEVER prints or logs the message body or the code. It reads `doorCode` from a fresh `GET /reservations/{id}`, never a cached copy.
- Button labels and custom ids, verbatim: `✅ وافق — أرسل الرمز` = `cg_send`, `📝 أرسلته يدوياً` = `cg_manual`, `↩️ تراجع` = `cg_undo`. Remove `cg_release` and `LABEL_RELEASE`.
- Verdict labels, verbatim: `✅ كتب «أوافق»`, `⚠️ رد بس مو واضح`, `⏳ ما رد بعد`.
- Code-only room: topic is exactly `codegate-room:1 codegate-res:<res_id>`. Name is `<channel_name(unit)[:60]>-code`. Category is Turnovers (`get_category`) via `_make_channel_spill`. On failure, call `_turnover_create_failed_alert`.
- Every room close posts one audit line to `CLEANING_REVIEW_CHANNEL` (`#oujact-review`).
- **Soak (switch OFF):**
  - cards go only into turnover rooms that already exist;
  - no code-only rooms, no holds, no re-posts, no alerts;
  - send and manual buttons are hidden;
  - the soak note stays.
- Every non-gated unit and every manual admin delete command behaves exactly as today.
- brain.db rules apply (closing(connect()), no WAL). New columns are added via `_LATE_COLUMNS`.
- Blocking work never runs on the Discord event loop: use `flow.run_blocking` and defer interactions first.
- The verification routine (CLAUDE.md) must pass. The only allowed full-suite failures are the 4 pre-existing date tests: `test_ops_capture` ×2, `test_train_export` ×1, `test_mot_flow.TestClose` ×1.

## Review Focus

1. **The turnover room opens after 09:00, when checkout is later than 21:00.** Expected: no code-only room while a departure exists today; the card lands in the turnover room when it appears; fallback to a code-only room only at check-in − 2h. (R2 `test_waits_for_late_turnover_room`, `test_fallback_code_room_at_2h`.)
2. **Hostaway has no door code for the booking** (manual-code units, or `doorCode` empty). Expected: `cg_send` refuses with a clear message; nothing is recorded; `cg_manual` records it. (R2 `test_send_empty_code_refuses_and_records_nothing`, R3 `test_send_code_empty_doorcode`.)
3. **Hostaway rejects the send** (an error, the kill switch, a duplicate claim). Expected: the release is undone, the card stays waiting, the presser sees why, and there is no double send on a second press. (R2 `test_send_failure_undoes_release`, R3 `test_sender_honours_kill_switch_and_dedupe`.)
4. **Someone deletes the room by hand while the code is unsent.** Expected (live only): the next tick re-posts the card, in the turnover room if one now exists, else in a code-only room. In soak: nothing. (R2 `test_lost_card_reposted_when_live`, `test_lost_card_dropped_in_soak`.)
5. **Cleaning is approved before the code is sent.** Expected: the room is not deleted, the close is recorded as pending, and the room is deleted right after the code is sent with an audit line. If the code is sent first, cleaning approval deletes the room normally. (R2 `test_pending_close_runs_after_send`, R3 `test_delete_guard_holds_and_records`.)

---

## File Structure

| File | Change |
|---|---|
| `codegate/engine.py` | `agree_verdict`, new labels/constants, `code_message`, card verdict line + buttons note; drop `LABEL_RELEASE`/`CONFIRM_TEXT` (replace with `CONFIRM_SEND`, `CONFIRM_SEND_UNCLEAR`, `CONFIRM_MANUAL`) |
| `codegate/db.py` | late columns `room_kind`, `room_close_pending`, `sent_by_bot`; helpers `set_room`, `set_close_pending`, `items_with_code_rooms(before_day=None)` |
| `codegate/host.py` | caps: `find_room`, `create_code_room`, `departures_today`, `send_code`, `delete_room`, `log_review`; remove `channel` |
| `codegate/flow.py` | placement, holds, send/manual/undo presses, room deletion, lost-card re-post, soak rules; drop headers |
| `bot.py` | bridge for the new caps; `_cg_send_code`; views; delete-site guards; remove `_cg_channel` |
| `tests/test_codegate_*.py` | updated + new tests |

---

### Task R1: Engine: verdict, code message, card

**Files:** Modify `codegate/engine.py`. Test `tests/test_codegate_engine.py`.

**Produces:**
- `agree_verdict(replies: list[dict]) -> str`: one of `"yes"`, `"unclear"`, `"none"`.
- `VERDICT_LABEL = {"yes": "✅ كتب «أوافق»", "unclear": "⚠️ رد بس مو واضح", "none": "⏳ ما رد بعد"}`.
- `LABEL_SEND = "✅ وافق — أرسل الرمز"`, `LABEL_MANUAL = "📝 أرسلته يدوياً"`, `LABEL_UNDO` unchanged.
- `CONFIRM_SEND = "يرسل البوت الرمز للضيف الحين من Hostaway. متأكد إنه كتب «أوافق»؟"`.
- `CONFIRM_SEND_UNCLEAR = "⚠️ ما لقيت «أوافق» واضحة في ردوده. لو قرأت ردّه وتأكدت إنه موافق، كمّل — غير كذا اطلب منه يكتبها أول."`.
- `CONFIRM_MANUAL = "سجّل إنك أرسلت الرمز بنفسك من Hostaway؟"`.
- `code_message(code: str) -> str`: the bilingual text below, with the code inserted and a trailing `#`.
- `card(item, now, soak=False)`: adds a field `ما كتبه الضيف` = `VERDICT_LABEL[agree_verdict(replies)]`, placed before the quoted replies. Footer becomes `«تسليم الرموز» · البوت يقرأ الرد ويرسل الرمز فقط لما تضغط الزر`. Description: `اقرأ رد الضيف، ثم اضغط «✅ وافق — أرسل الرمز». لو Hostaway ما عنده رمز للحجز، أرسله يدوياً واضغط «📝 أرسلته يدوياً».`.

`agree_verdict` rules:
- Fold each reply with `_fold`, then remove tatweel and Arabic diacritics.
- `none` if `replies` is empty.
- `yes` if ANY reply contains an agree token AND that same reply has no negation before the token.
  - Agree tokens: `أوافق`, `اوافق`, `موافق`, `موافقه`, `موافقة`, `agree`, `agreed`, `i agree`, `okay agree`.
  - Negation (whole word, before the token, same reply): `ما`, `لا`, `مو`, `مب`, `مش`, `غير`, `don't`, `dont`, `do not`, `not`, `disagree`, `never`.
- Otherwise `unclear`.

```python
def code_message(code):
    c = str(code).strip()
    return ("🔑 كود الدخول: %s ثم #\n"
            "يشتغل الكود من وقت الدخول — لو احتجت أي شي حنا هنا 🤍\n\n"
            "🔑 Door code: %s then #\n"
            "The code works from check-in time — anything you need, we're right here 🤍") % (c, c)
```

- [ ] Step 1: Write failing tests:
  - `test_verdict_yes_variants` covers `أوافق على قواعد الشقة`, `اوافق`, `موافق 👍`, `I agree`, `agreed!`, `ok agree`.
  - `test_verdict_negations_are_unclear` covers `ما أوافق`, `لا اوافق`, `I don't agree`, `not agree`, `disagree`.
  - `test_verdict_unclear` covers `IGR RA`, `ok`, `what rules?`.
  - `test_verdict_none`.
  - `test_code_message_has_code_twice_and_hash`: `code_message("1234")` contains `1234 ثم #` and `1234 then #`.
  - `test_card_shows_verdict_field`.
  - `test_labels_verbatim`.
- [ ] Step 2: Run `python3 -m unittest tests.test_codegate_engine -v` and confirm they FAIL.
- [ ] Step 3: Implement. Update the existing card/label tests that referenced `LABEL_RELEASE`/`CONFIRM_TEXT`; keep their intent.
- [ ] Step 4: Run tests until GREEN, and run pyflakes on `codegate/engine.py`.
- [ ] Step 5: Commit `feat(codegate): agreement verdict, code message, card shows what the guest wrote`.

---

### Task R2: Flow + db: rooms, holds, send/manual/undo, deletion

**Files:** Modify `codegate/db.py`, `codegate/host.py`, `codegate/flow.py`. Test `tests/test_codegate_db.py` and `tests/test_codegate_flow.py`.

**New HOST capabilities** (document each in host.py; remove `channel`):
- `find_room` BLOCKING `(lid, day) -> channel_id | None`: the turnover room for `oujact-key:<lid>:<day>`.
- `create_code_room` async `(item) -> channel_id | None`: opens the code-only room. Returns None on failure; the bot side alerts.
- `departures_today` BLOCKING `(day) -> set[int]`: listing ids with a confirmed departure that day.
- `send_code` BLOCKING `(res_id, conversation_id) -> (ok: bool, why: str)`:
  - `why` ∈ `"sent"`, `"no_code"`, `"killed"`, `"duplicate"`, `"error"`;
  - it does the fresh reservation read and the send, and RAISES nothing.
- `delete_room` async `(channel_id, reason) -> bool`.
- `log_review` async `(text) -> None`: one line to `#oujact-review`.

**db changes:**
- `_LATE_COLUMNS` gains `room_kind TEXT` (`"turnover"` | `"code"`), `room_close_pending INTEGER DEFAULT 0` and `sent_by_bot INTEGER DEFAULT 0`.
- `set_room(res_id, channel_id, kind)` clears `card_message_id`/`card_hash` when the channel changes.
- `set_close_pending(res_id, on)`.
- `mark_sent_by_bot(res_id)`.
- `code_room_items(older_than_day=None)` returns rows with `room_kind="code"` and a channel_id, optionally only `day < older_than_day`.
- `release()` stays first-wins. `undo()` also clears `sent_by_bot`.
- `_DAY_RESET` gains `room_kind` and `room_close_pending`.

**flow changes:**
1. **Placement**, per item, live and soak, before `_render`. When the item has no `channel_id`, or HOST.edit reported the message gone:
   - `room = find_room(lid, day)`. If found → `set_room(kind="turnover")`.
   - Else, if live:
     - `lid in departures_today(day)` and now < check-in − 2h → wait (no card yet);
     - otherwise `create_code_room(item)` → `set_room(kind="code")`.
   - Else (soak) → no card.
   - `departures_today` is fetched once per tick, and only when some item needs placement.
2. **Headers are dropped** (remove the header block from tick; keep `db.header_*` unused or delete them with their tests). The card's content mentions the coverer (`_mention`).
3. **Lost card**: if `HOST.edit` returns False for an existing card:
   - live → clear `channel_id`/`card_message_id` (`set_room(None, None)`), so placement re-runs next tick;
   - soak → leave it.
4. **Buttons** (`_buttons`):
   - soak → `[]` (no buttons; the soak note explains);
   - live and released → `["undo"]`;
   - live and not released → `["send", "manual"]`;
   - cancelled → `[]`.
5. **`press_send(message_id, presser)`**:
   - Checks, in order: item found; not cancelled; live; not released; `may_release`. If any fails, refuse with the existing wording style.
   - Then `db.release(...)` first-wins. If it loses: «أُرسل من قبل — …».
   - Then `ok, why = await run_blocking(HOST.send_code, res_id, conversation_id)`.
   - `ok` → `mark_sent_by_bot`, `set_code_seen(True)`, `event("code_sent_bot", presser)`, re-render (green), run `_after_code_sent(item)`. Return `(True, "تم ✅ — أرسلت الرمز للضيف.")`.
   - not ok → `db.undo(res_id, "system", now)`, `event("code_send_failed", why)`, re-render. Return `(False, msg)`:
     - `no_code` → «Hostaway ما فيه رمز لهذا الحجز — أرسله يدوياً من Hostaway ثم اضغط «📝 أرسلته يدوياً».»
     - `killed` → «الإرسال للضيوف موقوف حالياً (مفتاح الإيقاف).»
     - `duplicate` → «هذي الرسالة انرسلت قبل شوي — ما أرسلتها مرتين.»
     - `error` → «Hostaway ما رد — جرّب بعد دقيقة.»
6. **`press_manual(message_id, presser)`**:
   - Same checks as send, except it also works in soak.
   - `db.release` → event `code_manual` → re-render.
   - Honesty check applies as before (live only).
   - `_after_code_sent` runs once code_seen becomes 1, from the tick's honesty check.
7. **`press_undo`**: admin only, as today. It corrects the record only (the message text says so: «صححت السجل — الرسالة اللي انرسلت ما تنحذف.»).
8. **`_after_code_sent(item)`**:
   - `room_kind == "code"` → `delete_room(channel_id, "codegate: code sent")`.
   - `room_kind == "turnover"` and `room_close_pending` → `delete_room(...)` and `set_close_pending(False)`.
   - Every delete → `log_review("🔑 أُرسل الرمز · <unit> · <guest> · <by> · HH:MM")`.
   - A failed delete is logged and does not raise.
9. **Room cleanup in tick** (live only):
   - Code-only rooms of cancelled items → delete.
   - Code-only rooms from days before today → delete. Use `code_room_items(older_than_day=today)`.
   - A manual record whose honesty check later finds the code → `_after_code_sent`.
10. **Hold API for bot.py:**
    - `should_hold(lid, day) -> bool`, BLOCKING: True when live, the lid is gated, and an item for (lid, day) exists, is not cancelled, and has no `released_at`.
    - `defer_close(lid, day) -> None`: sets `room_close_pending` on that item.
11. **Alerts** stay as today, but are posted into the item's room (`channel_id`). An item with no room yet still escalates to #escalations.

- [ ] Step 1: Write failing tests (fake HOST with the new caps):
  - `test_card_goes_into_turnover_room`
  - `test_code_room_when_no_departure`
  - `test_waits_for_late_turnover_room`
  - `test_fallback_code_room_at_2h`
  - `test_soak_only_existing_turnover_rooms_no_buttons`
  - `test_send_success_records_green_and_deletes_code_room`
  - `test_send_empty_code_refuses_and_records_nothing`
  - `test_send_failure_undoes_release`
  - `test_send_double_press_one_send`
  - `test_manual_records_then_honesty_deletes_code_room`
  - `test_pending_close_runs_after_send`
  - `test_turnover_room_not_deleted_without_pending`
  - `test_should_hold_matrix` (live/soak, released, cancelled, other unit)
  - `test_lost_card_reposted_when_live`
  - `test_lost_card_dropped_in_soak`
  - `test_cancelled_code_room_deleted`
  - `test_old_code_room_deleted_next_day`
  - `test_alerts_post_into_room`
  - `test_audit_line_on_every_delete`
  - db: `test_late_columns_added`, `test_set_room_clears_card`, `test_day_change_resets_room`
- [ ] Step 2: Run and confirm RED.
- [ ] Step 3: Implement. Update or remove tests that asserted the old channel/headers/`release` button. Keep the go-live pre-check, soak and alert tests passing; adapt the fakes.
- [ ] Step 4: Run `python3 -m unittest tests.test_codegate_engine tests.test_codegate_db tests.test_codegate_flow -v` until GREEN, and confirm pyflakes is clean.
- [ ] Step 5: Commit `feat(codegate): cards live in the turnover room, code-only rooms, send/manual buttons, held room close`.

---

### Task R3: bot.py bridge, code sender, views, delete guards

**Files:** Modify `bot.py`. Test `tests/test_codegate_bot.py`.

Re-read the lines around every anchor before editing. bot.py is ~76k lines.

1. **Remove** `_cg_channel` and its wiring. Keep `_cg_post`/`_cg_edit`.
2. **`_cg_find_room(lid, day)`** BLOCKING-safe (it only reads the guild cache): look up `str(lid)+":"+day` in `_cw_channels_in(bot.get_guild(GUILD_ID))` and return its `channel_id` or None.
3. **`async _cg_create_code_room(item)`**:
   - `guild = bot.get_guild(GUILD_ID)`; `category = await get_category(guild)`.
   - `name = channel_name(item["unit"])[:60] + "-code"`; `topic = "codegate-room:1 codegate-res:%s" % item["res_id"]`.
   - `ch = await _make_channel_spill(guild, category, name, topic=topic)`; return `str(ch.id)`.
   - On exception: `await _turnover_create_failed_alert(guild, item["unit"], e)` and return None.
4. **`_cg_departures_today(day)`**: listing ids of confirmed departures that day, via `_ha_reservations_window("departureStartDate","departureEndDate",day,day)` (CONFIRMED_STATUSES only).
5. **`_cg_send_code(res_id, conversation_id) -> (ok, why)`**, the ONLY code-sending path:

```python
def _cg_send_code(res_id, conversation_id):
    """«تسليم الرموز»: send the door code for ONE reservation, after a staff press + confirm.
    The only path in the bot that may send a code: it deliberately does not go through
    send_guest_message's code-leak firewall, and so it must never log the body or the code."""
    if ASSISTANT_SEND_KILL:
        return False, "killed"
    try:
        r = (api_get(f"/reservations/{res_id}") or {}).get("result") or {}
    except Exception as e:
        print("[codegate] reservation read failed:", type(e).__name__)
        return False, "error"
    code = str(r.get("doorCode") or "").strip()
    if not code or not conversation_id:
        return False, "no_code"
    claim = f"codegate-send:{res_id}"
    if not _once_claim(claim):
        return False, "duplicate"
    try:
        api_post(f"/conversations/{conversation_id}/messages",
                 {"body": with_signature(_codegate.engine.code_message(code)),
                  "communicationType": "email"})
        log_event("guest", f"تسليم الرموز · أُرسل الرمز · حجز {res_id}")
        return True, "sent"
    except Exception as e:
        _once_release(claim)
        print("[codegate] code send failed:", type(e).__name__)
        return False, "error"
```

   Before writing it, check `_once_claim`/`_once_release`/`with_signature`/`log_event` signatures and the claim TTL. A dedupe that expires before a legitimate re-send matters only after an undo; an admin undo should release the claim, so add `_once_release(f"codegate-send:{res_id}")` inside the undo path via a HOST cap or the view. Note the `print` uses only the exception type, never the message.
6. **`_cg_delete_room(channel_id, reason)`**: fetch the channel and `delete(reason=reason)`. Return False on NotFound/Forbidden or any error, and log it.
7. **`_cg_log_review(text)`**: same as `_ready_log_review`. Reuse it if it fits; otherwise post the same way to `CLEANING_REVIEW_CHANNEL`.
8. **Wire** the new caps in `_cg_wire` and remove `channel`.
9. **Views**:
   - `CodegateView` has three persistent buttons: `cg_send` (success), `cg_manual` (secondary), `cg_undo` (secondary). `_CG_CUSTOM_ID` maps `send`/`manual`/`undo`.
   - The `cg_send` click reads the item (`run_blocking(db.item_by_message)`) and the verdict. It then opens a confirm view showing `CONFIRM_SEND`, or `CONFIRM_SEND_UNCLEAR` when the verdict is not "yes".
   - Confirm → `defer(ephemeral=True)` → `flow.press_send(...)` → `_cw_reply(msg)`.
   - `cg_manual` → confirm `CONFIRM_MANUAL` → `defer` → `flow.press_manual`.
   - `cg_undo` → `defer` → `flow.press_undo`.
   - The presser lookup stays in `run_blocking`.
10. **Delete-site guards**: add `_cg_hold_room(lid, date_iso) -> bool`, which calls `flow.should_hold` safely (any error → False) and, when True, calls `flow.defer_close`.
    - Discord Approve (~15813–15822): before `interaction.channel.delete` / `tch.delete`. If `_cg_hold_room(lid, date)` → skip the delete and reply/log «الغرفة تبقى مفتوحة لين ينرسل رمز الدخول».
    - Dashboard approve (~58156): same guard before `tch.delete`.
    - `_ready_close_channel` (~16208): same guard at its top.
    - Each guarded site already runs in an async context, so wrap `_cg_hold_room` in `await asyncio.to_thread(...)`, or the codegate pool (`_codegate.flow.run_blocking`). Request handlers must NOT use `asyncio.to_thread` (web-lane rule, CLAUDE.md), so use `_codegate.flow.run_blocking` in the dashboard handler.
    - Find `lid`/`date` from the variables already in scope at each site; re-read them.
11. **`!ouja رموز`** reports placement counts (`turnover`/`code`/`waiting`), and live/soak as today.

- [ ] Step 1: Write failing tests:
  - `test_view_has_send_manual_undo`
  - `test_click_dispatches_send` (ViewStore)
  - `test_send_code_happy_path`: patch `api_get` → `doorCode "1234"`, patch `api_post` to capture; assert the body contains `1234 ثم #` and `communicationType == "email"`; capture stdout and assert the code is NOT printed.
  - `test_send_code_empty_doorcode`
  - `test_sender_honours_kill_switch_and_dedupe`: kill switch on → "killed" and no post; second call → "duplicate".
  - `test_send_failure_releases_claim`
  - `test_find_room_uses_turnover_key` (fake guild via `_cw_channels_in` patch)
  - `test_code_room_name_and_topic` (patch `_make_channel_spill`)
  - `test_delete_guard_holds_and_records`: patch `flow.should_hold` True → the guarded function does not delete; `defer_close` called.
  - `test_delete_guard_off_for_non_gated` and `test_firewall_untouched`: `send_guest_message` still blocks a code body.
  - No network: keep the module-level `_api_request` fence.
- [ ] Step 2: Run and confirm RED.
- [ ] Step 3: Implement.
- [ ] Step 4: GREEN:
  - `py_compile -W error::SyntaxWarning`
  - pyflakes 0 new
  - the 4 codegate modules
  - watchdog + musaed tests
  - `grep -n "api.hostaway.com"` on the test output → none
- [ ] Step 5: Commit `feat(codegate): bot bridge — turnover-room cards, code-only rooms, the one code sender, held room close`.

---

### Task R4: Docs + go-live steps

**Files:** `docs/superpowers/plans/2026-10-21-house-rules-code-release.md` (Task 8), and the spec §5 if needed.

- [ ] Plan Task 8:
  - The saved-reply step becomes optional. The bot now sends the code; the saved reply stays useful for manual sends.
  - Add a step: the test booking end to end with the real `cg_send`.
  - Note that `doorCode` availability is checked live with `!ouja رموز` (count of today's gated arrivals with a code), never displaying a code.
- [ ] `!ouja رموز` (R3) also reports `code_available=N/M` for today's live gated arrivals without revealing any code. If not done in R3, add it here with a test.
- [ ] Commit `docs(codegate): go-live steps for revision 2`.
