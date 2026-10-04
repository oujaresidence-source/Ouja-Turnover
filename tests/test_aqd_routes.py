# -*- coding: utf-8 -*-
"""
«العقود» — the HTTP boundary, attacked where the rules are actually reachable: a viewer
writing, an ops user countersigning, a phone guessing digits, a double-tapped sign button,
a blank canvas, a stranger's name, an unapproved template.

Fake IDs are built by concatenation (permits/tools_privacy_scan.py stays green).
Run: python3 -m unittest tests.test_aqd_routes
"""

import asyncio
import base64
import datetime
import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aiohttp import web                                               # noqa: E402

from aqd import db, files, host, routes                               # noqa: E402
from brain import db as bdb                                           # noqa: E402
from tests.test_aqd_engine import NID, individual, unit, company      # noqa: E402

os.environ["AQD_ENABLED"] = "1"


class _Headers(dict):
    def get(self, k, d=None):
        for kk, v in self.items():
            if kk.lower() == k.lower():
                return v
        return d


class _Req:
    def __init__(self, body=None, role="admin", query=None, match=None, ip="10.0.0.1", actor="فيصل",
                 authed=True):
        self._body = body if body is not None else {}
        self.query = dict(query or {})
        self.match_info = dict(match or {})
        self.role = role
        self.actor_name = actor
        self.authed = authed
        self.method = "POST" if body is not None else "GET"
        self.headers = _Headers({"User-Agent": "UnitTest/1.0", "X-Forwarded-For": ip})
        self.remote = ip

    async def json(self):
        return self._body


def json_response(data, status=200):
    return {"status": status, "data": json.loads(json.dumps(data, ensure_ascii=False))}


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def body(resp):
    return resp["data"]


async def _wt(fn, *a, **kw):
    return fn(*a, **kw)


class Recorder:
    def __init__(self):
        self.payloads = []
        self.fail = False

    def __call__(self, payload):
        if self.fail:
            raise RuntimeError("discord is down")
        self.payloads.append(payload)


def png(ink=True, w=400, h=150):
    from PIL import Image, ImageDraw
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    if ink:
        d = ImageDraw.Draw(im)
        d.line([(20, 100), (120, 30), (220, 110), (330, 40), (380, 90)], fill=(29, 35, 32, 255), width=5)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def boot(prefix="aqd_"):
    tmp = tempfile.mkdtemp(prefix=prefix)
    bdb.set_db_path_for_tests(os.path.join(tmp, "brain.db"))
    db.reset_init_cache()
    routes.LIMITER.reset()
    rec = Recorder()
    host.wire({
        "dash_auth": lambda r: getattr(r, "authed", True),
        "req_role": lambda r: getattr(r, "role", "viewer"),
        "actor": lambda r: getattr(r, "actor_name", "—"),
        "json_response": json_response,
        "web": web,
        "state_dir": tmp,
        "now": lambda: datetime.datetime.now(routes.RIYADH),
        "web_thread": _wt,
        "listings": lambda: [{"id": 7, "name": "Ouja | الملقا 1", "active": True}],
        "notify": rec,
        "log_event": lambda c, t: None,
        "public_base": lambda: "https://ouja.test",
        "discord_ids": lambda: {"فيصل": "998877665544332211"},
    })
    return rec, tmp


def future(days=20):
    return (datetime.date.today() + datetime.timedelta(days=days)).isoformat()


def answers(**over):
    a = individual(units=[unit(delivery_date=future())])
    a.update(over)
    return a


class Base(unittest.TestCase):
    def setUp(self):
        os.environ["AQD_PDF_DISABLED"] = "1"
        self.rec, self.tmp = boot()

    def save(self, a=None, role="admin", actor="فيصل"):
        r = body(run(routes.api_save(_Req({"answers": a or answers()}, role=role, actor=actor))))
        self.assertTrue(r.get("ok"), r)
        return r["id"]

    def send(self, cid):
        r = body(run(routes.api_send(_Req({"id": cid}))))
        self.assertTrue(r.get("ok"), r)
        return r

    def token(self, cid):
        return db.get(cid)["token"]

    def approve(self):
        r = body(run(routes.api_settings(_Req({"approve": True, "confirm": "اعتماد"}))))
        self.assertTrue(r["approval"]["approved"], r)

    def verify(self, tok, last4=None, ip="10.0.0.1"):
        return body(run(routes.api_public_verify(_Req({"token": tok, "last4": last4 or NID[-4:]}, ip=ip))))

    def sent_and_verified(self, a=None):
        cid = self.save(a)
        self.send(cid)
        tok = self.token(cid)
        v = self.verify(tok)
        self.assertTrue(v["ok"], v)
        return cid, tok, v["view_key"]

    def sign(self, tok, key, **over):
        b = {"token": tok, "view_key": key, "typed_name": "عبدالله محمد الشمري", "consent": True,
             "signature_png_b64": png()}
        b.update(over)
        return body(run(routes.api_public_sign(_Req(b))))


class TestRoles(Base):

    def test_anonymous_is_401_on_the_logged_in_api(self):
        r = run(routes._safe(routes.api_list)(_Req(authed=False)))
        self.assertEqual(r["status"], 401)

    def test_viewer_cannot_write(self):
        for fn in (routes.api_save, routes.api_send, routes.api_preview, routes.api_void, routes.api_resend):
            r = run(fn(_Req({"answers": answers(), "id": 1}, role="viewer")))
            self.assertEqual(r["status"], 403, fn.__name__)

    def test_ops_cannot_countersign_or_approve(self):
        r = run(routes.api_countersign(_Req({"id": 1}, role="ops")))
        self.assertEqual(r["status"], 403)
        r = run(routes.api_settings(_Req({"approve": True, "confirm": "اعتماد"}, role="ops")))
        self.assertEqual(r["status"], 403)
        self.assertFalse(routes.is_approved())

    def test_approval_needs_the_exact_word(self):
        r = body(run(routes.api_settings(_Req({"approve": True, "confirm": "اعتمد"}))))
        self.assertFalse(r["ok"])
        self.assertFalse(routes.is_approved())
        self.approve()
        self.assertEqual(routes.approval()["by"], "فيصل")

    def test_void_is_admin_or_creator_and_needs_a_reason(self):
        cid = self.save(actor="نورة", role="ops")
        r = run(routes.api_void(_Req({"id": cid, "reason": "تجربة"}, role="ops", actor="ناصر")))
        self.assertEqual(r["status"], 403)
        r = body(run(routes.api_void(_Req({"id": cid, "reason": ""}, role="ops", actor="نورة"))))
        self.assertFalse(r["ok"])
        r = body(run(routes.api_void(_Req({"id": cid, "reason": "العميل تراجع"}, role="ops", actor="نورة"))))
        self.assertTrue(r["ok"], r)
        self.assertEqual(db.get(cid)["status"], "void")


class TestDraftAndSend(Base):

    def test_db_never_holds_the_full_id(self):
        cid = self.save()
        row = db.get(cid)
        self.assertNotIn(NID, json.dumps(row, ensure_ascii=False))
        self.assertEqual(row["id_last4"], NID[-4:])
        self.assertIn(NID, json.dumps(files.read_json(cid, "draft_answers.json")))
        self.send(cid)
        self.assertFalse(files.exists(cid, "draft_answers.json"))
        self.assertIn(NID, files.read_text(cid, "frozen.html"))
        self.assertNotIn(NID, json.dumps(db.get(cid), ensure_ascii=False))
        got = body(run(routes.api_get(_Req(query={"id": cid}))))
        self.assertNotIn(NID, json.dumps(got, ensure_ascii=False))
        self.assertEqual(got["contract"]["id_masked"], "••••••" + NID[-4:])

    def test_jamiya_unknown_blocks_send(self):
        cid = self.save(answers(jamiya="unknown"))
        r = body(run(routes.api_send(_Req({"id": cid}))))
        self.assertFalse(r["ok"])
        self.assertIn("جمعية الملاك", r["error"])
        self.assertEqual(db.get(cid)["status"], "draft")

    def test_send_freezes_hashes_and_links(self):
        cid = self.save()
        r = self.send(cid)
        row = db.get(cid)
        self.assertEqual(row["status"], "sent")
        self.assertTrue(r["link"].startswith("https://ouja.test/sign/"))
        self.assertIn("wa.me/966555123456", r["wa_url"])
        from aqd import engine
        self.assertEqual(row["doc_sha256"], engine.doc_hash(files.read_text(cid, "frozen.html").encode("utf-8")))
        self.assertGreaterEqual(len(row["token"]), 40)
        # a sent contract can no longer be edited
        r = body(run(routes.api_save(_Req({"id": cid, "answers": answers(op_pct="25")}))))
        self.assertFalse(r["ok"])

    def test_preview_returns_html_with_watermark_and_errors(self):
        r = body(run(routes.api_preview(_Req({"answers": answers(full_name="")}))))
        self.assertTrue(r["ok"])
        self.assertIn("full_name", r["errors"])
        self.assertIn("نموذج غير معتمد للتوقيع", r["html"])
        self.assertNotIn("base64,", r["html"].split("</style>")[0][:2000])

    def test_list_counts(self):
        a = self.save()
        b = self.save()
        self.send(b)
        r = body(run(routes.api_list(_Req())))
        self.assertEqual(r["counts"], {"draft": 1, "sent": 1})
        self.assertEqual(r["awaiting_countersign"], 0)
        self.assertEqual({x["id"] for x in r["rows"]}, {a, b})


class TestPublic(Base):

    def test_public_read_shows_no_body_before_verify(self):
        cid = self.save()
        self.send(cid)
        r = body(run(routes.api_public_get(_Req(match={"token": self.token(cid)}))))
        self.assertTrue(r["ok"])
        self.assertEqual(r["greeting"], "عبدالله")
        self.assertNotIn("html", r)
        dump = json.dumps(r, ensure_ascii=False)
        self.assertNotIn(NID, dump)
        self.assertNotIn("الطرف الأول", dump)

    def test_a_draft_token_or_junk_is_invalid(self):
        r = body(run(routes.api_public_get(_Req(match={"token": "x" * 43}))))
        self.assertEqual(r["state"], "invalid")

    def test_wrong_token_and_wrong_digits_look_identical(self):
        cid = self.save()
        self.send(cid)
        a = self.verify("y" * 43, "0000", ip="10.0.0.9")
        b = self.verify(self.token(cid), "0000", ip="10.0.0.8")
        self.assertEqual(a, b)
        self.assertEqual(sorted(a.keys()), ["error", "ok"])

    def test_five_wrong_tries_lock_and_the_right_digits_stay_refused(self):
        cid = self.save()
        self.send(cid)
        tok = self.token(cid)
        for i in range(5):
            self.assertFalse(self.verify(tok, "0000", ip="10.0.1.%d" % i)["ok"])
        r = self.verify(tok, ip="10.0.2.1")
        self.assertFalse(r["ok"])
        self.assertTrue(r.get("locked"))
        self.assertIsNone(db.get(cid)["view_key"])
        # once locked_until passes, the right digits work again
        db.update(cid, locked_until="2000-01-01T00:00:00")
        self.assertTrue(self.verify(tok, ip="10.0.2.2")["ok"])

    def test_verify_returns_the_document_and_a_view_key(self):
        cid, tok, key = self.sent_and_verified()
        self.assertEqual(db.get(cid)["status"], "verified")
        self.assertGreaterEqual(len(key), 24)
        v = self.verify(tok)
        self.assertIn("الطرف الأول", v["html"])
        self.assertIn("نموذج غير معتمد للتوقيع", v["html"])
        self.assertFalse(v["can_sign"])

    def test_open_counts_once_per_ten_minutes_per_ip(self):
        cid = self.save()
        self.send(cid)
        tok = self.token(cid)
        for _ in range(3):
            run(routes.api_public_open(_Req({"token": tok})))
        run(routes.api_public_open(_Req({"token": tok}, ip="10.9.9.9")))
        row = db.get(cid)
        self.assertEqual(row["status"], "opened")
        self.assertEqual(row["open_count"], 2)
        self.assertTrue(row["first_open_at"])

    def test_rate_limit_per_token(self):
        cid = self.save()
        self.send(cid)
        tok = self.token(cid)
        rs = [body(run(routes.api_public_get(_Req(match={"token": tok}, ip="10.3.%d.1" % i)))) for i in range(12)]
        self.assertTrue(rs[0]["ok"])
        self.assertEqual(rs[-1]["state"], "busy")


class TestSign(Base):

    def test_refused_while_template_unapproved(self):
        _cid, tok, key = self.sent_and_verified()
        r = self.sign(tok, key)
        self.assertFalse(r["ok"])
        self.assertIn("قيد المراجعة القانونية", r["error"])

    def test_refusals(self):
        self.approve()
        cid, tok, key = self.sent_and_verified()
        for over, needle in (({"consent": False}, "توافق"),
                             ({"consent": "true"}, "توافق"),
                             ({"signature_png_b64": png(ink=False)}, "فاضي"),
                             ({"signature_png_b64": "data:image/png;base64,QUJD"}, "PNG"),
                             ({"typed_name": "Mickey Mouse"}, "ما يطابق"),
                             ({"view_key": "wrong-key-wrong-key-wrong"}, "التحقق")):
            r = self.sign(tok, key, **over)
            self.assertFalse(r["ok"], over)
            self.assertIn(needle, r["error"], over)
        self.assertEqual(db.get(cid)["status"], "verified")
        self.assertEqual(self.rec.payloads, [])

    def test_refused_when_unverified_expired_or_void(self):
        self.approve()
        cid = self.save()
        self.send(cid)
        tok = self.token(cid)
        r = self.sign(tok, "no-key")
        self.assertFalse(r["ok"])                       # never verified
        v = self.verify(tok)
        db.update(cid, expires_at="2000-01-01T00:00:00")
        r = self.sign(tok, v["view_key"])
        self.assertFalse(r["ok"])
        self.assertIn("انتهت صلاحية", r["error"])
        self.assertEqual(db.get(cid)["status"], "expired")
        cid2, tok2, key2 = self.sent_and_verified()
        run(routes.api_void(_Req({"id": cid2, "reason": "خطأ في البيانات"})))
        r = self.sign(tok2, key2)
        self.assertFalse(r["ok"])
        self.assertIn("أُلغي", r["error"])

    def test_sign_succeeds_once_and_notifies_once_even_on_double_submit(self):
        self.approve()
        cid, tok, key = self.sent_and_verified()
        r1 = self.sign(tok, key)
        self.assertTrue(r1["ok"], r1)
        r2 = self.sign(tok, key)
        self.assertFalse(r2["ok"])
        row = db.get(cid)
        self.assertEqual(row["status"], "signed_owner")
        self.assertTrue(files.exists(cid, "signature.png"))
        self.assertTrue(files.exists(cid, "signed.html"))       # PDF disabled -> HTML fallback
        self.assertEqual(len(self.rec.payloads), 1)
        p = self.rec.payloads[0]
        self.assertEqual(p["kind"], "signed")
        self.assertIn(row["ref"], p["text"])
        self.assertIn("<@998877665544332211>", p["text"])
        self.assertNotIn(NID, p["text"])
        self.assertNotIn("555123456", p["text"])
        self.assertTrue(row["notified_signed_at"])
        run(routes.api_list(_Req()))                              # the retry tick must not re-post
        self.assertEqual(len(self.rec.payloads), 1)
        self.assertIn("سجل التوقيع الإلكتروني", files.read_text(cid, "signed.html"))

    def test_a_failed_notify_is_retried_by_the_list_tick(self):
        self.approve()
        self.rec.fail = True
        cid, tok, key = self.sent_and_verified()
        self.assertTrue(self.sign(tok, key)["ok"])
        self.assertIsNone(db.get(cid)["notified_signed_at"])
        self.rec.fail = False
        r = body(run(routes.api_list(_Req())))
        self.assertEqual(r["awaiting_countersign"], 1)
        self.assertEqual(len(self.rec.payloads), 1)
        run(routes.api_list(_Req()))
        self.assertEqual(len(self.rec.payloads), 1)

    def test_company_verifies_with_cr_and_rep_name(self):
        self.approve()
        a = company(units=[unit(delivery_date=future())])
        cid = self.save(a)
        self.send(cid)
        tok = self.token(cid)
        from tests.test_aqd_engine import CR
        v = self.verify(tok, CR[-4:])
        self.assertTrue(v["ok"], v)
        r = self.sign(tok, v["view_key"], typed_name="سعد الدوسري")
        self.assertTrue(r["ok"], r)


class TestCountersign(Base):

    def _upload_operator(self):
        r = body(run(routes.api_settings(_Req({"values": {"op_rep_name": "فيصل العوجا", "op_wakala_no": "123",
                                                          "op_wakala_date": "01/01/2026م"},
                                               "op_sig_png": png(), "op_stamp_png": png()}))))
        self.assertTrue(r["ok"], r)

    def test_countersign_needs_signature_and_stamp_then_completes(self):
        self.approve()
        cid, tok, key = self.sent_and_verified()
        self.assertTrue(self.sign(tok, key)["ok"])
        r = body(run(routes.api_countersign(_Req({"id": cid}))))
        self.assertFalse(r["ok"])
        self.assertIn("الختم", r["error"])
        self._upload_operator()
        r = body(run(routes.api_countersign(_Req({"id": cid}))))
        self.assertTrue(r["ok"], r)
        row = db.get(cid)
        self.assertEqual(row["status"], "completed")
        self.assertTrue(files.exists(cid, "final.pdf") or files.exists(cid, "final.html"))
        self.assertEqual([p["kind"] for p in self.rec.payloads], ["signed", "completed"])
        r = body(run(routes.api_countersign(_Req({"id": cid}))))
        self.assertFalse(r["ok"])
        r = body(run(routes.api_void(_Req({"id": cid, "reason": "محاولة"}))))
        self.assertFalse(r["ok"])
        # the client's same link now serves the final copy
        v = self.verify(tok)
        self.assertEqual(v["state"], "completed")
        p, _ct, _fn = routes.core_public_file(tok, v["view_key"])
        self.assertTrue(p.endswith(("final.pdf", "final.html")))

    def test_settings_reject_non_png(self):
        r = body(run(routes.api_settings(_Req({"op_sig_png": "data:image/png;base64," +
                                                base64.b64encode(b"GIF89a....").decode()}))))
        self.assertFalse(r["ok"])


class TestEndToEnd(unittest.TestCase):
    """Synthetic end-to-end in a temp STATE_DIR with the REAL PDF engine."""

    def test_create_send_open_verify_approve_sign_countersign_pdf(self):
        from aqd import pdf
        if pdf._renderer() is None:
            self.skipTest("the shared renderer needs Python 3.12+ (Railway runs 3.13) — gate G9 runs it there")
        os.environ.pop("AQD_PDF_DISABLED", None)
        rec, _tmp = boot("aqd_e2e_")
        t = Base("setUp")
        t.rec = rec
        cid = t.save()
        t.send(cid)
        tok = t.token(cid)
        run(routes.api_public_open(_Req({"token": tok})))
        v = t.verify(tok)
        self.assertTrue(v["ok"], v)
        t.approve()
        r = t.sign(tok, v["view_key"])
        self.assertTrue(r["ok"], r)
        TestCountersign._upload_operator(t)
        r = body(run(routes.api_countersign(_Req({"id": cid}))))
        self.assertTrue(r["ok"], r)
        row = db.get(cid)
        self.assertEqual(row["status"], "completed")
        self.assertTrue(files.exists(cid, "final.pdf"), "the shared Chromium did not produce final.pdf")
        import fitz
        doc = fitz.open(files.path(cid, "final.pdf"))
        text = "".join(pg.get_text() for pg in doc)
        self.assertGreater(doc.page_count, 5)
        compact = "".join(text.split())
        for needle in (row["ref"], "الشمري", "سجلالتوقيعالإلكتروني"):
            self.assertIn(needle, compact if " " not in needle else text, needle)
        self.assertEqual([p["kind"] for p in rec.payloads], ["signed", "completed"])


if __name__ == "__main__":
    unittest.main()
