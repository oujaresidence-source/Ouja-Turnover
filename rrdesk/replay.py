# -*- coding: utf-8 -*-
"""
rrdesk.replay — run a real (redacted) RR room through rrdesk offline and print its timeline.

    python3 -m rrdesk.replay tests/fixtures/rrdesk/rooms_replay/<room>.json [--now ISO] [--auto]

No Discord, no network, no model: a temporary brain.db, a fake clock that steps through the
room minute by minute (ticking the ladder like the live loop), and the classification recorded
in the fixture (`label` on Sam's messages) instead of a model call. This is how a future bug
report gets reproduced: export the room, redact it, replay it, read the timeline.

Fixture shape:
    {"name": "...", "ticket": {"seq": 47, "code": "HMXXXX", "lid": 1, "opener": "staff-1"},
     "people": {"Sam": "sam", "staff-1": "team", "bot": "bot"},
     "messages": [{"id": "1", "at": "2026-09-11T14:42:54+03:00", "who": "Sam",
                   "text": "...", "media": 0, "voice": false, "mentions": ["staff-1"],
                   "label": {"is_request": true, "asks": ["photos"], "confidence": 0.9}}],
     "presses": [{"at": "...", "who": "staff-1", "kind": "deliver", "request": 1}]}
"""

import datetime
import json
import os
import sys
import tempfile

NL = chr(10)


def _ids(people):
    """Stable fake Discord ids per role label (sam = 555, team members 101.., bot 777)."""
    out, n = {}, 101
    for name, role in sorted((people or {}).items()):
        if role == "sam":
            out[name] = "555"
        elif role == "bot":
            out[name] = "777"
        else:
            out[name] = str(n)
            n += 1
    return out


def replay(room, now=None, auto=False):
    """Run the room; every global this swaps (the model call, digests, board, HOST
    capabilities) is put back afterwards, so a replay never leaks into the caller."""
    from . import flow, translate
    from .host import HOST
    saved = {"call_model": translate.call_model, "_digests": flow._digests, "_board": flow._board,
             "host": dict(vars(HOST))}
    try:
        return _replay(room, now, auto)
    finally:
        translate.call_model = saved["call_model"]
        flow._digests, flow._board = saved["_digests"], saved["_board"]
        for k in list(vars(HOST)):
            if k not in saved["host"]:
                delattr(HOST, k)
        for k, v in saved["host"].items():
            setattr(HOST, k, v)


def _replay(room, now=None, auto=False):
    from brain import db as bdb
    from ops import db as odb, engine as oeng
    from ops.host import HOST as OPS_HOST
    from . import db, flow, translate
    from .host import HOST

    tmp = tempfile.mkdtemp(prefix="rrdesk_replay_")
    bdb.set_db_path_for_tests(os.path.join(tmp, "brain.db"))
    db.reset_init_cache()
    odb.reset_init_cache()
    translate.reset_glossary_cache()
    tz = oeng.tz()
    people = room.get("people") or {}
    ids = _ids(people)
    team = [n for n, r in people.items() if r == "team"]
    t = room.get("ticket") or {}
    rec = {"kind": "rr", "seq": t.get("seq") or 1, "code": t.get("code") or "HMXXXX",
           "status": "new", "lid": t.get("lid") or 1,
           "opener_id": ids.get(t.get("opener") or "", "")}
    clock = {"t": None}
    HOST.now = lambda: clock["t"]
    HOST.guild_id = 1
    HOST.rr_record = lambda cid: rec if str(cid) == "900" else None
    HOST.rr_records = lambda: {"900": rec}
    HOST.enrich = lambda code: dict(room.get("enrich") or {"days_left": 10})
    first_team = team[0] if team else ""
    HOST.responsible_for = lambda lid, day: (first_team, ids.get(first_team, ""), "owner")
    HOST.lead_id = lambda: ids.get(room.get("lead") or "", "") or "100"
    HOST.on_leave = lambda name, day: False
    HOST.off_today = lambda name, day: False
    HOST.employees = lambda: [{"name": n, "did": ids[n]} for n in team]
    HOST.once_claim = lambda name, ttl=None: True
    HOST.watchdog_channel = lambda: "غرفة-المراقبة"
    HOST.public_base = lambda: ""
    OPS_HOST.public_base = lambda: ""
    OPS_HOST.discord_ids = lambda: {n: ids[n] for n in team}
    db.set_setting("sam_ids", "555")
    db.set_setting("detect_mode", "auto" if auto else (room.get("detect_mode") or "confirm"))
    labels = {}

    def fake_call(content, max_tokens=0, system=None, poster=None):
        body = content if isinstance(content, str) else json.dumps(content)
        msg = body.split("MESSAGE:" + NL)[-1]
        lab = labels.get(msg.strip())
        if lab is not None and "is_request" in body:
            import re as _re
            keep = " ".join(_re.findall("⟦[0-9]+⟧", msg))
            d = {"translation": ("[translated] " + keep).strip(), "is_request": bool(lab.get("is_request")),
                 "confidence": float(lab.get("confidence", 0.9 if lab.get("is_request") else 0.1)),
                 "asks": lab.get("asks") or [], "urgent": bool(lab.get("urgent")),
                 "summary_en": lab.get("summary_en") or msg[:120], "summary_ar": lab.get("summary_ar") or ""}
            return json.dumps(d, ensure_ascii=False), 300, 40
        if body.startswith("Translate every string value"):
            return body[body.index("{"):], 300, 80
        import re as _re
        keep = " ".join(_re.findall("⟦[0-9]+⟧", msg))         # a faithful fake keeps placeholders
        return json.dumps({"translation": ("[translated] " + keep).strip()}), 200, 30
    translate.call_model = fake_call

    msgs = sorted(room.get("messages") or [], key=lambda m: m["at"])
    presses = sorted(room.get("presses") or [], key=lambda p: p["at"])
    if not msgs:
        return ["(empty room)"]
    start = datetime.datetime.fromisoformat(msgs[0]["at"]).astimezone(tz)
    end = datetime.datetime.fromisoformat(now).astimezone(tz) if now else (
        datetime.datetime.fromisoformat(msgs[-1]["at"]).astimezone(tz) + datetime.timedelta(days=2))
    lines = []
    seen_outbox = set()

    def drain_log():
        for r in db.q("SELECT * FROM rrdesk_outbox ORDER BY id"):
            if r["id"] in seen_outbox:
                continue
            seen_outbox.add(r["id"])
            p = db.loads(r["payload_json"], {})
            what = (p.get("content") or p.get("text") or "").replace(chr(0x2063), "").strip()
            if not what and p.get("embeds"):
                e = p["embeds"][0]
                what = (e.get("title") or e.get("description") or "")[:80]
            where = p.get("channel_name") or ("dm" if r["kind"] == "dm" else "room")
            lines.append("%s  → %-6s %-8s %s" % (clock["t"].strftime("%m-%d %H:%M"), r["kind"], where,
                                                 what.replace(NL, " ")[:110]))
            mid = "p:" + r["ref"]
            flow.delivered({"payload": p}, {"message_ids": [mid]})
            db.execute("UPDATE rrdesk_outbox SET state='done' WHERE id=?", (r["id"],))

    flow._digests = lambda now: {}            # replay shows the room, not the 13:00 digests
    flow._board = lambda now: 0

    def next_stop(after):
        """The next moment anything can happen: a message, a press, a ladder step, an
        auto-confirm. Jumping between them replays two months in a second."""
        cands = []
        if mi < len(msgs):
            cands.append(datetime.datetime.fromisoformat(msgs[mi]["at"]).astimezone(tz))
        if pi < len(presses):
            cands.append(datetime.datetime.fromisoformat(presses[pi]["at"]).astimezone(tz))
        cfg = flow.sla_cfg()
        from . import engine as _e
        for r in db.live_requests():
            for st in _e.ladder(r["state"], db.parse(r["clock_at"]), bool(r["urgent"]), cfg):
                if st["at"] > after:
                    cands.append(st["at"])
            if r["state"] == _e.DELIVERED and db.parse(r.get("delivered_at")):
                cands.append(db.parse(r["delivered_at"]) + datetime.timedelta(hours=_e.AUTO_CONFIRM_HOURS))
        if not _e.in_work_hours(after):           # a due step waits for 11:00
            d0 = after.date() if after.hour >= 11 else after.date()
            cands.append(datetime.datetime(d0.year, d0.month, d0.day, 11, 0, 30, tzinfo=tz))
        cands = [c for c in cands if c > after]
        return min(cands) if cands else None

    def _simulate_delivery(d, m, ids_):
        """History has no button presses. With simulate_delivery the replay presses «سلّمت» for
        the team when they actually delivered: files posted after a file request, or a real
        text answer (3+ words) to a question-only request. The misses left are genuine."""
        from . import engine as _e
        words = len([w for w in (m.get("text") or "").split() if not w.startswith("@")])
        low = (m.get("text") or "").lower()
        none = any(k in low for k in ("there is no", "dont have", "don't have", "not available",
                                      "ما عندنا", "مافي", "ما فيه"))
        for r in db.live_requests("900"):
            if r["state"] not in _e.LIVE or not r.get("card_message_id"):
                continue
            if none:
                ok, _t = flow.press("unavailable", r["card_message_id"],
                                    {"did": d["author_id"], "name": m["who"]}, {"note": m.get("text")}, clock["t"])
                if ok:
                    lines.append("%s  [simulated: %s presses ما عندنا on #%d]"
                                 % (clock["t"].strftime("%m-%d %H:%M"), m["who"], r["id"]))
                continue
            files = bool(set(r["asks"]) & _e.FILE_ASKS)
            if (files and int(m.get("media") or 0) > 0) or (not files and words >= 3):
                ok, _t = flow.press("deliver", r["card_message_id"],
                                    {"did": d["author_id"], "name": m["who"]}, {"proof": True}, clock["t"])
                if ok:
                    lines.append("%s  [simulated: %s presses سلّمت on #%d]"
                                 % (clock["t"].strftime("%m-%d %H:%M"), m["who"], r["id"]))

    mi = pi = 0
    t_ = start
    while t_ is not None and t_ <= end:
        while mi < len(msgs) and datetime.datetime.fromisoformat(msgs[mi]["at"]).astimezone(tz) <= t_:
            m = msgs[mi]
            clock["t"] = datetime.datetime.fromisoformat(m["at"]).astimezone(tz)
            role = people.get(m["who"], "team")
            if role == "sam" and m.get("label") is not None:
                # keyed by the MASKED text — that is what the model call sees
                labels[translate.protect((m.get("text") or "").strip())[0]] = m["label"]
            d = {"id": str(m["id"]), "channel_id": "900", "parent_id": None,
                 "author_id": ids.get(m["who"], "0"), "author_name": m["who"],
                 "is_bot": role == "bot", "is_self": False, "text": m.get("text") or "",
                 "embeds": [{"title": "", "description": x, "fields": [], "footer": ""}
                            for x in m.get("embeds") or []],
                 "media": [{"url": "x", "content_type": "image/jpeg"}] * int(m.get("media") or 0),
                 "voice": bool(m.get("voice")),
                 "mention_ids": [ids[x] for x in m.get("mentions") or [] if x in ids],
                 "reference_author_id": ids.get(m.get("reply_to") or "", None),
                 "role_mentioned": bool(m.get("role_mention")), "bot_ids": ["777"], "at": clock["t"]}
            lines.append("%s  %-8s %s" % (clock["t"].strftime("%m-%d %H:%M"), m["who"][:8],
                                          (m.get("text") or ("[voice]" if m.get("voice") else "[%d file]" % int(m.get("media") or 0)))
                                          .replace(NL, " ")[:110]))
            flow.on_message(d)
            if room.get("simulate_delivery") and role == "team":
                _simulate_delivery(d, m, ids)
            if role == "sam" and m.get("pin"):
                flow.on_pin("900", None, d["id"], "555", "555", d["text"], clock["t"])
            drain_log()
            mi += 1
        while pi < len(presses) and datetime.datetime.fromisoformat(presses[pi]["at"]).astimezone(tz) <= t_:
            p = presses[pi]
            clock["t"] = datetime.datetime.fromisoformat(p["at"]).astimezone(tz)
            req = db.request(int(p.get("request") or 1))
            if req and req.get("card_message_id"):
                ok, text = flow.press(p["kind"], req["card_message_id"],
                                      {"did": ids.get(p["who"], "0"), "name": p["who"]},
                                      {"proof": True, "note": p.get("note"), "reason": p.get("reason")},
                                      clock["t"])
                lines.append("%s  [%s presses %s] %s" % (clock["t"].strftime("%m-%d %H:%M"), p["who"],
                                                         p["kind"], "ok" if ok else "refused: " + text))
            drain_log()
            pi += 1
        clock["t"] = t_
        flow.tick(t_)
        drain_log()
        nxt = next_stop(t_)
        t_ = max(nxt, t_ + datetime.timedelta(seconds=1)) if nxt else None
    lines.append("")
    for r in db.recent_requests(50)[::-1]:
        lines.append("request #%d: %s · path %s · owner %s (rule %s) · rework %s"
                     % (r["id"], r["state"], r["path"], r.get("owner_name") or r.get("owner_did"),
                        r.get("owner_rule"), r.get("rework")))
    for ms in db.q("SELECT * FROM rrdesk_misses ORDER BY id"):
        lines.append("miss: request #%d gen %d · eligible %d · verdict %s"
                     % (ms["request_id"], ms["gen"], ms["eligible"], ms.get("verdict")))
    for d in odb.dry_rows(kind="rr_warning"):
        lines.append("would-be warning: %s %s" % (d["period_key"], d["detail"]))
    return lines


def main(argv=None):
    argv = list(argv if argv is not None else sys.argv[1:])
    if not argv:
        print(__doc__)
        return 2
    now, auto = None, False
    if "--now" in argv:
        i = argv.index("--now")
        now = argv[i + 1]
        del argv[i:i + 2]
    if "--auto" in argv:
        argv.remove("--auto")
        auto = True
    with open(argv[0], encoding="utf-8") as f:
        room = json.load(f)
    print(NL.join(replay(room, now=now, auto=auto)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
