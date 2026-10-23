# -*- coding: utf-8 -*-
"""
tools/rr_history_export.py — READ-ONLY export of every RR-history room, for the RR Desk study.

    DISCORD_TOKEN=... DISCORD_GUILD_ID=... python3 tools/rr_history_export.py export
    python3 tools/rr_history_export.py analyze .rrdesk_study/raw/<file>.json [--sam <discord id>]

* Uses the bot token over the Discord REST API with GET requests only — no gateway connection,
  and no request that changes anything. tests/test_rrdesk_structure.py greps this file for
  any write verb.
* Never imports bot.py. Never prints or saves the token.
* At most one request every 250 ms; a 429 waits for its retry_after.
* Raw output goes to .rrdesk_study/raw/ (git-ignored). Nothing raw is ever committed: the
  committed fixtures are produced through rrdesk.study.redact().
The room set is rrdesk.study.is_history_room (brief §4.2): the RR family, the «📦 أرشيف N»
archive (old Ticket Tool rooms included), متابعه and تعويضات, and every thread inside them.
"""

import datetime
import json
import os
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

API = "https://discord.com/api/v10"
PAUSE_S = 0.25
_last = [0.0]


def _get(path, token):
    """One GET. Retries 429 with Discord's retry_after; returns parsed JSON or raises."""
    for _attempt in range(6):
        wait = PAUSE_S - (time.time() - _last[0])
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.time()
        req = urllib.request.Request(API + path, method="GET",
                                     headers={"Authorization": "Bot " + token,
                                              "User-Agent": "OujaRRDeskStudy (read-only, 1.0)"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429:
                try:
                    time.sleep(float(json.loads(e.read().decode("utf-8")).get("retry_after", 2)) + 0.2)
                except Exception:
                    time.sleep(2)
                continue
            if e.code in (403, 404):
                return None                     # a room the bot cannot read — the browser covers it
            raise
    raise RuntimeError("too many 429s on " + path.split("?")[0])


def _msg(m):
    a = m.get("author") or {}
    ref = (m.get("referenced_message") or {}).get("author") or {}
    flags = int(m.get("flags") or 0)
    return {"mid": m["id"], "who": a.get("global_name") or a.get("username") or "",
            "whoid": a.get("id") or "", "isbot": bool(a.get("bot")), "at": m.get("timestamp"),
            "txt": (m.get("content") or "")[:900], "media": len(m.get("attachments") or []), "files": 0,
            "voice": bool(flags & 8192), "ments": [u.get("id") for u in m.get("mentions") or []],
            "rep_whoid": ref.get("id"),
            "emb": [((e.get("title") or "") + chr(10) + (e.get("description") or ""))[:700]
                    for e in m.get("embeds") or []]}


def _history(cid, token):
    out, before = [], None
    while True:
        q = "/channels/%s/messages?limit=100" % cid + ("&before=%s" % before if before else "")
        page = _get(q, token)
        if not page:
            break
        out.extend(_msg(m) for m in page)
        before = page[-1]["id"]
        if len(page) < 100:
            break
    out.sort(key=lambda x: int(x["mid"]))
    return out


def export(out_dir):
    from rrdesk import study
    token = os.environ.get("DISCORD_TOKEN", "").strip()
    gid = os.environ.get("DISCORD_GUILD_ID", "").strip()
    if not token or not gid:
        print("DISCORD_TOKEN / DISCORD_GUILD_ID missing — nothing exported.")
        return 2
    chans = _get("/guilds/%s/channels" % gid, token) or []
    cats = {c["id"]: c.get("name") or "" for c in chans if c.get("type") == 4}
    rooms = []
    active = (_get("/guilds/%s/threads/active" % gid, token) or {}).get("threads") or []
    for c in chans:
        if c.get("type") != 0:
            continue
        cat = cats.get(c.get("parent_id"), "")
        if not study.is_history_room(c.get("name"), c.get("topic") or "", cat):
            continue
        msgs = _history(c["id"], token)
        threads = [t for t in active if t.get("parent_id") == c["id"]]
        arch = _get("/channels/%s/threads/archived/public?limit=100" % c["id"], token) or {}
        threads += arch.get("threads") or []
        for t in threads:
            msgs += _history(t["id"], token)
        msgs.sort(key=lambda x: int(x["mid"]))
        rooms.append({"room": {"id": c["id"], "name": c.get("name"), "cat": cat},
                      "topic": c.get("topic") or "", "complete": True, "msgs": msgs})
        print("  %-40s %4d messages" % (c.get("name"), len(msgs)))
    os.makedirs(out_dir, exist_ok=True)
    fn = os.path.join(out_dir, "api_%s.json" % datetime.date.today().isoformat())
    with open(fn, "w", encoding="utf-8") as f:
        json.dump({"source": "api", "guild": gid, "rooms": rooms}, f, ensure_ascii=False)
    print("wrote %s (%d rooms)" % (fn, len(rooms)))
    return 0


def analyze(path, sams):
    from rrdesk import study
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    rep = study.analyze(d.get("rooms") or [], sams)
    rep.pop("_requests", None)
    print(json.dumps(rep, ensure_ascii=False, indent=1, default=str))
    return 0


def main(argv):
    if not argv or argv[0] not in ("export", "analyze"):
        print(__doc__)
        return 2
    if argv[0] == "export":
        return export(os.path.join(ROOT, ".rrdesk_study", "raw"))
    sams = []
    if "--sam" in argv:
        sams.append(argv[argv.index("--sam") + 1])
    return analyze(argv[1], sams or ["1494059651032158409", "Sam1989"])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
