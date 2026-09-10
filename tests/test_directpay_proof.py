# -*- coding: utf-8 -*-
"""Proof of payment — the file that lets a collection room close.

  * no attachment ⇒ refused
  * a .txt ⇒ refused; an image ⇒ accepted; a PDF ⇒ accepted
  * a history-read EXCEPTION ⇒ refused. This is the OPPOSITE of bot._maint_has_proof, on
    purpose: the maintenance ticket fails open because trapping a maintenance room shut is
    worse than a weak close. Money is the reverse — if we cannot see the proof, we do not
    close. Asserted here so nobody "fixes" it later.
  * an oversized file ⇒ refused with the size in the message
  * the BYTES land on disk under STATE_DIR (a Discord attachment URL is signed and expires)
    and proof_meta carries filename / size / content_type / uploader

Run: python3 -m unittest tests.test_directpay_proof
"""
import asyncio
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import db as bdb                       # noqa: E402
from directpay import db, host, proof, service    # noqa: E402


class FakeAtt:
    def __init__(self, filename, content_type, data=b"x", size=None, boom=False):
        self.filename, self.content_type = filename, content_type
        self._data, self._boom = data, boom
        self.size = len(data) if size is None else size
        self.url = "https://cdn.discordapp.com/attachments/1/2/%s?ex=expires" % filename

    async def read(self):
        if self._boom:
            raise RuntimeError("cdn down")
        return self._data


class FakeAuthor:
    def __init__(self, name="أسيل", uid=22):
        self.display_name, self.id = name, uid


class FakeMsg:
    def __init__(self, attachments=(), author=None):
        self.attachments = list(attachments)
        self.author = author or FakeAuthor()


class FakeChannel:
    """history() is an async iterator, like discord.py's (newest first)."""
    def __init__(self, msgs=(), boom=False):
        self._msgs, self._boom = list(msgs), boom

    def history(self, limit=100):
        msgs, boom = self._msgs[:limit], self._boom

        class _It:
            def __aiter__(self_inner):
                self_inner._i = 0
                return self_inner

            async def __anext__(self_inner):
                if boom:
                    raise RuntimeError("discord is having a moment")
                if self_inner._i >= len(msgs):
                    raise StopAsyncIteration
                self_inner._i += 1
                return msgs[self_inner._i - 1]
        return _It()


def run(coro):
    return asyncio.run(coro)       # not get_event_loop — a sibling test may have closed it


class TestFindProof(unittest.TestCase):
    def test_no_attachment_is_refused(self):
        att, why = run(proof.find_proof(FakeChannel([FakeMsg(), FakeMsg()])))
        self.assertIsNone(att)
        self.assertEqual(why, "none")

    def test_txt_is_not_an_invoice(self):
        att, why = run(proof.find_proof(FakeChannel([FakeMsg([FakeAtt("notes.txt", "text/plain")])])))
        self.assertIsNone(att)
        self.assertEqual(why, "none")

    def test_image_is_accepted(self):
        a = FakeAtt("shot.png", "image/png")
        att, why = run(proof.find_proof(FakeChannel([FakeMsg([a])])))
        self.assertIs(att, a)
        self.assertEqual(why, "ok")

    def test_pdf_is_accepted(self):
        a = FakeAtt("invoice.pdf", "application/pdf")
        att, why = run(proof.find_proof(FakeChannel([FakeMsg([a])])))
        self.assertIs(att, a)

    def test_newest_qualifying_wins(self):
        new = FakeAtt("new.jpg", "image/jpeg")
        old = FakeAtt("old.pdf", "application/pdf")
        ch = FakeChannel([FakeMsg([FakeAtt("x.txt", "text/plain")]), FakeMsg([new]), FakeMsg([old])])
        att, _ = run(proof.find_proof(ch))
        self.assertIs(att, new)

    def test_history_read_error_FAILS_CLOSED(self):
        """The opposite of bot._maint_has_proof (which returns True on error). Money: if we
        cannot see the proof, we do not close."""
        att, why = run(proof.find_proof(FakeChannel(boom=True)))
        self.assertIsNone(att)
        self.assertEqual(why, "unreadable")
        self.assertIn("ما قدرت أقرأ", proof.reason_ar("unreadable"))


class TestSizeAndStore(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="dpproof_")
        bdb.set_db_path_for_tests(os.path.join(cls.tmp, "brain.db"))
        db.reset_init_cache()
        host.wire({"notify": None, "log_event": None, "state_dir": cls.tmp})

    def test_oversized_is_refused_with_the_size_message(self):
        a = FakeAtt("big.pdf", "application/pdf", size=13 * 1024 * 1024)
        ok, why = proof.check(a, max_mb=12)
        self.assertFalse(ok)
        self.assertIn("12", why)
        self.assertIn("13", why)
        ok, why = proof.check(FakeAtt("ok.pdf", "application/pdf", size=11 * 1024 * 1024), max_mb=12)
        self.assertTrue(ok, why)

    def test_bytes_land_on_disk_and_meta_is_complete(self):
        data = b"%PDF-1.4 fake invoice bytes"
        a = FakeAtt("Invoice #7 (Sept).pdf", "application/pdf", data=data)
        rel, meta = run(proof.store(self.tmp, "dp_abc", a, "أسيل", 22))
        self.assertTrue(rel.startswith("directpay/dp_abc/"))
        full = os.path.join(self.tmp, rel)
        self.assertTrue(os.path.exists(full))
        with open(full, "rb") as f:
            self.assertEqual(f.read(), data)
        self.assertEqual(meta["filename"], "Invoice #7 (Sept).pdf")
        self.assertEqual(meta["size"], len(data))
        self.assertEqual(meta["content_type"], "application/pdf")
        self.assertEqual(meta["uploader"], "أسيل")
        self.assertEqual(meta["uploader_id"], "22")
        self.assertNotIn("url", meta)                       # never the expiring link as the proof
        # a second proof for the same ticket gets its own numbered file
        rel2, _ = run(proof.store(self.tmp, "dp_abc", a, "أسيل", 22))
        self.assertNotEqual(rel, rel2)
        self.assertTrue(os.path.exists(os.path.join(self.tmp, rel2)))

    def test_a_failed_read_stores_nothing(self):
        a = FakeAtt("x.png", "image/png", boom=True)
        with self.assertRaises(Exception):
            run(proof.store(self.tmp, "dp_boom", a, "x", 1))
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "directpay", "dp_boom")) and
                         os.listdir(os.path.join(self.tmp, "directpay", "dp_boom")))

    def test_verified_close_needs_the_stored_path(self):
        t = db.open_ticket(reservation_id="9001", total_sar=1000.0, total_sar_current=1000.0,
                           created_at="2026-09-10T09:00:00")
        ok, why, info = service.attest_verified(t["id"], received_sar=1000.0, stayhub_ref="SH-1",
                                                proof_rel=None, proof_meta=None, by="فيصل", by_id="1")
        self.assertFalse(ok)
        self.assertEqual(db.ticket(t["id"])["status"], "open")
        ok, why, info = service.attest_verified(t["id"], received_sar=1000.0, stayhub_ref="SH-1",
                                                proof_rel="directpay/x/1_a.pdf",
                                                proof_meta={"filename": "a.pdf", "size": 3,
                                                            "content_type": "application/pdf"},
                                                by="فيصل", by_id="1")
        self.assertTrue(ok, why)
        row = db.ticket(t["id"])
        self.assertEqual(row["status"], "verified")
        self.assertEqual(row["proof_path"], "directpay/x/1_a.pdf")
        self.assertEqual(json.loads(row["proof_meta"])["filename"], "a.pdf")
        self.assertEqual(row["closed_by"], "فيصل")
        kinds = [e["kind"] for e in db.events(t["id"])]
        self.assertIn("verified", kinds)


if __name__ == "__main__":
    unittest.main()
