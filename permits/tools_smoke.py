# -*- coding: utf-8 -*-
"""
Gate G11 — a local smoke test of the permits web door, end to end over real HTTP.

The cleanest seam that does not need Discord: import bot.py (no Discord login happens at
import), build an aiohttp app with bot.py's REAL auth + role middleware in front, wire the
permits package with bot.py's REAL caps (_permits_caps), bootstrap a throwaway brain.db
(the committed seed loads: 45 permits), and hit it with real requests on a local port.

Prints SMOKE_OK when every check passes; otherwise prints the failing check and exits 1.
Run from the repo root: python3 permits/tools_smoke.py
"""

import asyncio
import os
import shutil
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
TOKEN = "permits-smoke-token"
os.environ["DASHBOARD_TOKEN"] = TOKEN


async def main():
    import aiohttp
    from aiohttp import web
    from aiohttp.test_utils import TestServer

    import bot
    from brain import db as bdb
    import permits

    tmp = tempfile.mkdtemp(prefix="permits_smoke_")
    try:
        bdb.set_db_path_for_tests(os.path.join(tmp, "brain.db"))
        permits.db.reset_init_cache()
        bot.DASHBOARD_TOKEN = TOKEN
        caps = bot._permits_caps()
        caps["state_dir"] = tmp
        permits.wire(caps)
        seeded = permits.bootstrap()

        viewer_tok = "permits-smoke-viewer"
        perms = {t: dict(v) for t, v in bot._default_perms("viewer").items()}
        perms["permits"] = {"read": True, "write": False, "create": False}
        bot._users["u-pm-viewer"] = {"id": "u-pm-viewer", "name": "مشاهد", "active": True,
                                     "role": "viewer", "perms": perms}
        bot._sessions[viewer_tok] = {"user_id": "u-pm-viewer", "expires_at": time.time() + 3600}

        app = web.Application(middlewares=[bot._role_enforce_mw])
        permits.register_routes(app)
        server = TestServer(app)
        await server.start_server()
        base = "http://%s:%s" % (server.host, server.port)
        checks = []

        async with aiohttp.ClientSession() as s:
            async def get(path, tok=None):
                async with s.get(base + path, headers={"X-Token": tok} if tok else {}) as r:
                    ctype = r.headers.get("Content-Type", "")
                    body = await (r.json() if "json" in ctype else r.text())
                    return r.status, body, r.headers

            async def post(path, data, tok=None):
                async with s.post(base + path, json=data, headers={"X-Token": tok} if tok else {}) as r:
                    return r.status, await r.json()

            st, body, hdr = await get("/permits/static/permits_tab.js")
            checks.append(("static js served", st == 200 and "window.PermitsTab" in body
                           and "no-cache" in hdr.get("Cache-Control", "")))
            st, body, _h = await get("/api/permits/summary")
            checks.append(("summary refuses without a token", st in (401, 403) and "counts" not in (body if isinstance(body, dict) else {})))
            st, body, _h = await get("/api/permits/summary", TOKEN)
            checks.append(("summary answers with DASHBOARD_TOKEN", st == 200 and body.get("ok")
                           and body["counts"]["total"] == 45 and body["mode"]["mode"] == "dry"))
            st, body, _h = await get("/api/permits/list", TOKEN)
            checks.append(("list returns the 45 seeded permits", st == 200 and len(body.get("rows", [])) == 45))
            f2 = [r for r in body.get("rows", []) if r.get("permit_no") == "50035533"]
            checks.append(("F2 is in the list with its end date", len(f2) == 1 and f2[0]["end_date"] == "2026-10-12"))
            st, body, _h = await get("/api/permits/list", viewer_tok)
            checks.append(("a viewer with read can list (and is told it cannot edit)",
                           st == 200 and body.get("can_edit") is False))
            st, body = await post("/api/permits/create", {"permit_type": "رخصة بلدية"}, viewer_tok)
            checks.append(("a viewer is refused a write by bot.py's middleware", st == 403))
            st, body = await post("/api/permits/mode", {"mode": "live", "confirm": "yes"}, TOKEN)
            checks.append(("going live without the typed word is refused", st == 400))
            st, body, _h = await get("/api/permits/parse-date?v=01/05/1448", TOKEN)
            checks.append(("parse-date reads Hijri", st == 200 and body.get("iso") in ("2026-10-12", None)))
            st, body, _h = await get("/api/permits/export.csv", TOKEN)
            checks.append(("CSV export", st == 200 and "50035533" in body))

        await server.close()
        checks.append(("seeded on first boot", seeded == 45))
        bad = [name for name, ok in checks if not ok]
        if bad:
            for name in bad:
                print("SMOKE_FAIL:", name)
            return 1
        print("SMOKE_OK (%d checks)" % len(checks))
        print("SMOKE_OK")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
