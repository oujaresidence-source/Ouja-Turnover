# -*- coding: utf-8 -*-
"""
Shared harness for the «ضم الوحدات» route tests: a temp brain.db, a wired HOST, and just
enough aiohttp request for these handlers. Imported by test_onb_routes and
test_onb_delegation — not a test module itself.
"""

import asyncio
import datetime
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import db as bdb                                  # noqa: E402
from onboarding import db, host                              # noqa: E402
from schedule import db as sdb                               # noqa: E402

EMPLOYEES = [("ناصر", "1111"), ("نورة", "2222"), ("عهود", "")]   # عهود has NO discord id


class _Req:
    """Just enough aiohttp request: a JSON body, a query string, path match info, a role."""

    def __init__(self, body=None, role="admin", query=None, match=None):
        self._body = body if body is not None else {}
        self.query = dict(query or {})
        self.match_info = dict(match or {})
        self.role = role
        self.method = "POST" if body is not None else "GET"

    async def json(self):
        return self._body


def json_response(data, status=200):
    return {"status": status, "data": data}


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def body(resp):
    return resp["data"]


class Recorder:
    """A fake HOST.notify that records every payload — and can be told to fail."""

    def __init__(self):
        self.payloads = []
        self.fail = False

    def __call__(self, payload):
        if self.fail:
            raise RuntimeError("discord is down")
        self.payloads.append(payload)

    def reset(self):
        self.payloads = []
        self.fail = False


def boot(prefix="onb_"):
    """Fresh temp brain.db + a seeded employee roster + a wired HOST. Returns the recorder."""
    tmp = tempfile.mkdtemp(prefix=prefix)
    bdb.set_db_path_for_tests(os.path.join(tmp, "brain.db"))
    db.reset_init_cache()
    sdb.reset_init_cache()
    for i, (name, _did) in enumerate(EMPLOYEES):
        sdb.execute("INSERT INTO schedule_employees (id, name, off_day, color, emoji, sort_order,"
                    " created_at) VALUES (?,?,?,?,?,?,?)",
                    (i + 1, name, i, "#B29A6A", "", i, db.now_iso()))
    rec = Recorder()
    host.wire({
        "dash_auth": lambda r: True,
        "req_role": lambda r: getattr(r, "role", "viewer"),
        "actor": lambda r: "فيصل",
        "json_response": json_response,
        "now": lambda: datetime.datetime(2026, 8, 30, 10, 0),
        "notify": rec,
        "log_event": lambda cat, txt: None,
        "discord_ids": lambda: {n: d for (n, d) in EMPLOYEES if d},
        "public_base": lambda: "https://ouja.test",
        "pmo_projects": lambda: {},
    })
    return rec


READY = {
    "client_name": "عبدالله الشمري", "client_type": "owner", "client_whatsapp": "0555000000",
    "unit_name": "الملقا 1 — دخول ذاتي", "district": "الملقا", "unit_kind": "tower",
    "bedrooms": 2, "furnish_state": "furnished",
}

FILL_TO_PUBLISH = {
    "strategy": "weekly_nightly", "ouja_rate_pct": 22, "cleaning_sar": 900,
    "contract_signed_at": "2026-08-01", "ceo_approval": "not_needed",
    "license_no": "LIC-99", "license_expiry": "2027-12-31",
    "photos_url": "https://drive/x", "photos_approved": 1,
    "access_notes": "المفتاح مع الحارس", "wifi_notes": "Ouja-Malqa / 12345678",
    "house_rules": "ممنوع الحفلات", "checkin_time": "15:00", "checkout_time": "12:00",
}


def make_ready(routes, pid, people=(1, 2)):
    """Drive a project all the way to a clean gate, through the real endpoints."""
    run(routes.api_update(_Req(dict(FILL_TO_PUBLISH, id=pid))))
    for eid in people:
        run(routes.api_assignee_add(_Req({"project_id": pid, "employee_id": eid})))
    for t in db.tasks(pid):
        if int(t["gate"] or 0) == 1 and (t["resolution"] or "open") == "open":
            run(routes.api_task_resolve(_Req({"project_id": pid, "task_id": t["id"],
                                              "resolution": "done"})))
