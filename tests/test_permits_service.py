# -*- coding: utf-8 -*-
"""
permits.service against a FakePort and a throwaway brain.db.

THE TWO PROMISES LOCKED HERE
  1. Never lose a permit: catch-up, retries with backoff, adoption after a crash,
     a replacement when a channel is deleted, nothing marked done on a failed check.
  2. Never double-notify: one live ticket per permit (the DB refuses a second), one
     digest per Riyadh day, one in-ticket reminder per day — across restarts and races.

Run: python3 -m unittest tests.test_permits_service
"""

import asyncio
import datetime
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import db as bdb                        # noqa: E402
from permits import db, engine, service            # noqa: E402
from permits.host import HOST                      # noqa: E402
from tests.permits_fakes import FakePort           # noqa: E402

TZ = datetime.timezone(datetime.timedelta(hours=3))


def at(iso, hour, minute=0):
    d = datetime.date.fromisoformat(iso)
    return datetime.datetime(d.year, d.month, d.day, hour, minute, tzinfo=TZ)


def run(coro):
    return asyncio.run(coro)


class Case(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="permits_svc_")
        bdb.set_db_path_for_tests(os.path.join(self.tmp, "brain.db"))
        db.reset_init_cache()
        self._saved = (HOST.maint_assignee_for, HOST.listings, HOST.dashboard_url)
        HOST.maint_assignee_for = lambda lid: ("ناصر", "111")
        HOST.listings = lambda: [{"id": 501, "internal_name": "Ouja | F2", "public_name": "", "active": True}]
        HOST.dashboard_url = lambda: "https://ouja.example/dashboard#permits"
        for k in ("PERMITS_FORCE_DRY", "PERMITS_PING_ROLE_ID", "PERMITS_ESCALATE_IDS"):
            os.environ.pop(k, None)
        self.port = FakePort()

    def tearDown(self):
        HOST.maint_assignee_for, HOST.listings, HOST.dashboard_url = self._saved
        shutil.rmtree(self.tmp, ignore_errors=True)

    def add(self, end, **over):
        data = {"permit_type": engine.SEED_TYPE, "permit_no": "50035533", "unit_text": "F2",
                "listing_id": 501, "end_date": end, "holder": "مالك", "scope": "unit"}
        data.update(over)
        return db.insert_permit(data, "test")

    def live(self):
        r = service.set_mode("live", service.CONFIRM_WORD, "admin")
        self.assertTrue(r["ok"], r)

    def tick(self, now, port=None):
        return run(service.tick(port or self.port, now))

    def tickets(self):
        return db.q("SELECT * FROM permits_tickets ORDER BY id")


class DryDefaultTest(Case):

    def test_a_fresh_db_is_dry(self):
        self.assertEqual(service.effective_mode(), "dry")

    def test_dry_writes_dry_rows_and_touches_no_discord(self):
        self.add("2026-10-05")
        self.tick(at("2026-10-01", 13))
        self.assertEqual(self.tickets(), [])
        self.assertEqual(self.port.calls, [])
        self.assertTrue(all(o["state"] == "dry" for o in db.outbox_rows()))
        self.assertEqual(len([o for o in db.outbox_rows() if o["kind"] == "open_ticket"]), 1)
        self.tick(at("2026-10-01", 14))                 # recorded once, not per tick
        self.assertEqual(len([o for o in db.outbox_rows() if o["kind"] == "open_ticket"]), 1)

    def test_force_dry_env_overrides_the_stored_mode(self):
        self.live()
        os.environ["PERMITS_FORCE_DRY"] = "1"
        try:
            self.assertEqual(service.effective_mode(), "dry")
            self.assertTrue(service.mode_info()["forced"])
            self.add("2026-10-05")
            self.tick(at("2026-10-01", 13))
            self.assertEqual(self.port.calls, [])
        finally:
            del os.environ["PERMITS_FORCE_DRY"]

    def test_going_live_needs_the_exact_word(self):
        for bad in ("", "شغل", "yes", "تشغيل التنبيهات"):
            r = service.set_mode("live", bad, "admin")
            self.assertFalse(r["ok"], bad)
            self.assertTrue(r["need_confirm"])
        self.assertEqual(service.effective_mode(), "dry")
        self.assertTrue(service.set_mode("live", "تشغيل", "admin")["ok"])
        self.assertEqual(service.effective_mode(), "live")
        self.assertTrue(service.set_mode("dry", "", "admin")["ok"])
        kinds = [e["kind"] for e in db.q("SELECT kind FROM permits_events")]
        self.assertEqual(kinds.count("mode_changed"), 2)


class OpenTest(Case):

    def test_live_opens_one_channel_with_name_topic_and_pinned_card(self):
        pid = self.add("2026-10-12")
        self.live()
        self.tick(at("2026-10-02", 13))
        chans = self.port.open_channels()
        self.assertEqual(len(chans), 1)
        cid, ch = list(chans.items())[0]
        t = self.tickets()[0]
        self.assertEqual(ch["name"], "تصريح-%03d-f2" % t["id"])
        self.assertEqual(ch["topic"], "ouja-permit: pid:%d tid:%d end:2026-10-12" % (pid, t["id"]))
        self.assertTrue(ch["messages"][0]["pinned"])
        self.assertEqual((t["state"], t["channel_id"]), ("open", cid))
        self.assertIn("<@111>", ch["card"]["content"])
        self.assertIn("ouja.example", json.dumps(ch["card"], ensure_ascii=False))

    def test_outside_the_window_it_waits_then_opens(self):
        self.add("2026-10-05")
        self.live()
        service.consume_golive_sweep()                  # not the first tick after go-live
        self.tick(at("2026-10-01", 23))
        self.assertEqual(self.tickets(), [])
        self.tick(at("2026-10-02", 9))
        self.assertEqual(len(self.tickets()), 1)

    def test_go_live_sweep_opens_expired_at_night_once(self):
        self.add("2026-09-20")
        self.add("2026-10-05", permit_no="2")
        self.live()
        self.tick(at("2026-10-01", 23))
        self.assertEqual(len(self.tickets()), 1)       # the expired one only
        self.tick(at("2026-10-01", 23, 30))
        self.assertEqual(len(self.tickets()), 1)       # the due one still waits for 09:00

    def test_last_tick_at_is_written(self):
        self.tick(at("2026-10-01", 13))
        self.assertTrue(db.get_setting("last_tick_at"))
        self.assertEqual(service.summary(at("2026-10-01", 13))["last_tick_at"], db.get_setting("last_tick_at"))

    def test_not_ready_skips_discord_and_marks_nothing(self):
        self.add("2026-10-05")
        self.live()
        self.tick(at("2026-10-01", 13), port=FakePort(ready=False))
        self.assertEqual(self.tickets(), [])
        self.tick(at("2026-10-01", 13, 5))
        self.assertEqual(len(self.port.open_channels()), 1)


class RaceTest(Case):

    def test_the_index_exists_and_refuses_a_second_live_ticket(self):
        pid = self.add("2026-10-05")
        db._ensure()
        with closing(sqlite3.connect(bdb.db_path())) as cx:
            idx = [r[0] for r in cx.execute("SELECT name FROM sqlite_master WHERE type='index'")]
            self.assertIn("idx_permits_one_live_ticket", idx)
            cx.execute("INSERT INTO permits_tickets(permit_id, state) VALUES(?, 'opening')", (pid,))
            with self.assertRaises(sqlite3.IntegrityError):
                cx.execute("INSERT INTO permits_tickets(permit_id, state) VALUES(?, 'open')", (pid,))
            cx.execute("INSERT INTO permits_tickets(permit_id, state) VALUES(?, 'closed')", (pid,))

    def test_open_ticket_row_twice_is_one_row(self):
        pid = self.add("2026-10-05")
        a = service.open_ticket_row(pid, at("2026-10-01", 13))
        b = service.open_ticket_row(pid, at("2026-10-01", 13))
        self.assertTrue(a)
        self.assertIsNone(b)
        self.assertEqual(len(self.tickets()), 1)

    def test_double_tick_is_one_channel(self):
        self.add("2026-10-05")
        self.live()
        self.tick(at("2026-10-01", 13))
        self.tick(at("2026-10-01", 13))
        self.assertEqual(len(self.port.open_channels()), 1)

    def test_two_copies_racing_make_one_channel(self):
        self.add("2026-10-05")
        self.add("2026-09-30", permit_no="9")
        self.live()

        async def both():
            await asyncio.gather(service.tick(self.port, at("2026-10-01", 13)),
                                 service.tick(self.port, at("2026-10-01", 13)))
        run(both())
        self.assertEqual(len(self.port.open_channels()), 2)
        self.assertEqual(len([c for c in self.port.calls if c[0] == "create"]), 2)

    def test_two_copies_with_their_own_ports_still_make_one_channel_each_permit(self):
        self.add("2026-10-05")
        self.live()
        p2 = FakePort()
        p2.channels = self.port.channels          # one Discord, two bot processes

        async def both():
            await asyncio.gather(service.tick(self.port, at("2026-10-01", 13)),
                                 service.tick(p2, at("2026-10-01", 13)))
        run(both())
        self.assertEqual(len(self.port.open_channels()), 1)

    def test_the_outbox_ref_is_unique(self):
        self.assertIsNotNone(db.enqueue("digest", "digest:2026-10-01", {}))
        self.assertIsNone(db.enqueue("digest", "digest:2026-10-01", {}))


class FailureTest(Case):

    def test_crash_after_create_is_adopted_not_duplicated(self):
        self.add("2026-10-05")
        self.live()
        self.port.crash_after_create = True
        self.tick(at("2026-10-01", 13))
        self.assertEqual(self.tickets()[0]["state"], "opening")
        self.tick(at("2026-10-01", 13, 10))            # backoff (1 min) has passed
        self.assertEqual(len(self.port.channels), 1)
        t = self.tickets()[0]
        self.assertEqual(t["state"], "open")
        self.assertEqual(t["channel_id"], list(self.port.channels)[0])

    def test_an_adopted_empty_channel_gets_its_card(self):
        self.add("2026-10-05")
        self.live()
        self.port.crash_before_card = True
        self.tick(at("2026-10-01", 13))
        self.tick(at("2026-10-01", 13, 10))
        self.assertEqual(len(self.port.channels), 1)
        ch = list(self.port.channels.values())[0]
        self.assertTrue(ch["card"] and ch["buttons"])
        t = self.tickets()[0]
        self.assertEqual((t["state"], t["card_msg_id"]), ("open", ch["card_msg_id"]))
        kinds = [e["kind"] for e in db.q("SELECT kind FROM permits_events")]
        self.assertIn("ticket_adopted", kinds)

    def test_stale_opening_with_a_dead_claim_is_reconciled(self):
        pid = self.add("2026-10-05")
        self.live()
        tid = service.open_ticket_row(pid, at("2026-10-01", 12, 0))
        db.execute("UPDATE permits_outbox SET state='claimed', claimed_at=? WHERE ref=?",
                   (service._utc(at("2026-10-01", 12, 0)), "open:t%d" % tid))
        self.tick(at("2026-10-01", 12, 5))             # claim only 5 min old: left alone
        self.assertEqual(self.port.channels, {})
        self.tick(at("2026-10-01", 12, 20))            # 20 min: reset and retried
        self.assertEqual(len(self.port.channels), 1)
        self.assertEqual(db.ticket(tid)["state"], "open")

    def test_discord_error_fails_backs_off_and_shows_in_the_digest(self):
        self.add("2026-10-05")
        self.live()
        self.port.fail_create = RuntimeError("Missing Permissions")
        self.tick(at("2026-10-01", 13))
        o = db.outbox("open:t%d" % self.tickets()[0]["id"])
        self.assertEqual((o["state"], o["attempts"]), ("failed", 1))
        self.assertIn("Missing Permissions", o["last_error"])
        self.assertIn("Missing Permissions", self.tickets()[0]["last_error"])
        creates = len([c for c in self.port.calls if c[0] == "create"])
        self.tick(at("2026-10-01", 13, 0))             # before the backoff — no retry
        self.assertEqual(len([c for c in self.port.calls if c[0] == "create"]), creates)
        digest = "\n".join(self.port.digests[-1][0])
        self.assertIn("⚠️ مشاكل النظام", digest)
        self.assertIn("Missing Permissions", digest)
        self.port.fail_create = None
        self.tick(at("2026-10-01", 13, 2))
        self.assertEqual(self.tickets()[0]["state"], "open")

    def test_backoff_schedule(self):
        self.assertEqual([service.backoff_minutes(n) for n in (1, 2, 3, 4, 5, 9)], [1, 5, 15, 60, 60, 60])

    def test_a_deleted_channel_is_replaced_with_a_note(self):
        self.add("2026-10-05")
        self.live()
        self.tick(at("2026-10-01", 13))
        old = self.tickets()[0]
        self.port.delete_channel(old["channel_id"])
        self.tick(at("2026-10-01", 14))
        ts = self.tickets()
        self.assertEqual(ts[0]["state"], "lost")
        self.assertEqual(ts[1]["state"], "open")
        card = self.port.channels[ts[1]["channel_id"]]["card"]
        self.assertIn("#%03d انحذفت" % old["id"], card["description"])
        kinds = [e["kind"] for e in db.q("SELECT kind FROM permits_events")]
        self.assertIn("ticket_lost", kinds)

    def test_cannot_check_is_never_deleted(self):
        self.add("2026-10-05")
        self.live()
        self.tick(at("2026-10-01", 13))
        self.port.fail_exists = RuntimeError("Discord unreachable")
        self.port.delete_channel(self.tickets()[0]["channel_id"])
        self.tick(at("2026-10-01", 14))
        self.assertEqual([t["state"] for t in self.tickets()], ["open"])


class ReminderTest(Case):

    def open_one(self, end, now):
        pid = self.add(end)
        self.live()
        self.tick(now)
        return pid, self.tickets()[0]

    def posts(self, cid):
        return [m for m in self.port.messages(cid) if "text" in m]

    def test_one_reminder_per_day_not_on_the_opening_day(self):
        _pid, t = self.open_one("2026-10-09", at("2026-10-01", 10))
        self.tick(at("2026-10-01", 13))
        self.assertEqual(self.posts(t["channel_id"]), [])      # the card was today's nudge
        self.tick(at("2026-10-02", 12))
        self.assertEqual(self.posts(t["channel_id"]), [])      # before 13:00
        self.tick(at("2026-10-02", 13))
        self.tick(at("2026-10-02", 18))
        self.assertEqual(len(self.posts(t["channel_id"])), 1)
        self.tick(at("2026-10-03", 13, 5))
        self.assertEqual(len(self.posts(t["channel_id"])), 2)

    def test_a_claim_never_silences(self):
        _pid, t = self.open_one("2026-10-09", at("2026-10-01", 10))
        service.claim(t["id"], "فهد", "222", "فهد")
        self.tick(at("2026-10-02", 13))
        msgs = self.posts(t["channel_id"])
        self.assertEqual(len(msgs), 1)
        self.assertIn("مستلمها **فهد**", msgs[0]["text"])

    def test_escalation_by_band(self):
        os.environ["PERMITS_PING_ROLE_ID"] = "555"
        os.environ["PERMITS_ESCALATE_IDS"] = "9,10"
        try:
            _pid, t = self.open_one("2026-10-05", at("2026-10-01", 10))
            self.tick(at("2026-10-02", 13))                    # 3 days → urgent
            m = self.posts(t["channel_id"])[-1]
            self.assertEqual((m["users"], m["roles"]), (["111"], ["555"]))
            self.tick(at("2026-10-07", 13))                    # −2 → expired
            m = self.posts(t["channel_id"])[-1]
            self.assertEqual((m["users"], m["roles"]), (["111", "9", "10"], []))
            self.assertIn("🔴 منتهي", m["text"])
        finally:
            del os.environ["PERMITS_PING_ROLE_ID"]
            del os.environ["PERMITS_ESCALATE_IDS"]

    def test_riyadh_midnight(self):
        _pid, t = self.open_one("2026-10-09", at("2026-09-30", 10))
        self.tick(at("2026-10-01", 23, 59))
        self.assertEqual(len(self.posts(t["channel_id"])), 1)
        self.tick(at("2026-10-02", 0, 1))
        self.assertEqual(len(self.posts(t["channel_id"])), 1)   # new day, but before 13:00


class DigestTest(Case):

    def test_once_per_day_across_ticks_and_a_restart(self):
        self.add("2026-10-05")
        self.live()
        self.tick(at("2026-10-01", 12))
        self.assertEqual(self.port.digests, [])
        self.tick(at("2026-10-01", 13, 5))
        db.reset_init_cache()                                   # "restart"
        port2 = FakePort()
        port2.channels = self.port.channels
        self.tick(at("2026-10-01", 13, 10), port=port2)
        self.tick(at("2026-10-01", 20))
        self.assertEqual(len(self.port.digests) + len(port2.digests), 1)
        self.assertEqual(db.get_setting("digest_date"), "2026-10-01")
        self.tick(at("2026-10-02", 13))
        self.assertEqual(len(self.port.digests), 2)

    def test_latch_only_after_a_successful_send(self):
        self.add("2026-12-05")
        self.live()
        self.port.fail_post = RuntimeError("503")
        self.tick(at("2026-10-01", 13))
        self.assertIsNone(db.get_setting("digest_date"))
        self.port.fail_post = None
        self.tick(at("2026-10-01", 13, 3))
        self.assertEqual(db.get_setting("digest_date"), "2026-10-01")
        self.assertEqual(len(self.port.digests), 1)

    def test_renewed_yesterday_shows(self):
        pid = self.add("2026-10-05")
        self.live()
        self.tick(at("2026-10-01", 10))
        service.renew(pid, "2027-10-05", "ناصر", "2026-10-01", proof=True, via="discord")
        self.tick(at("2026-10-02", 13))
        text = "\n".join(self.port.digests[-1][0])
        self.assertIn("✅ تجدّد أمس", text)
        self.assertIn("ناصر", text)


class RenewTest(Case):

    def setUp(self):
        super().setUp()
        self.pid = self.add("2026-10-05")
        self.live()
        self.tick(at("2026-10-01", 10))
        self.t = self.tickets()[0]

    def test_renewal_chains_closes_and_locks(self):
        r = service.renew(self.pid, "05/10/2027", "ناصر", "2026-10-01", new_no="5009", proof=True, via="discord")
        self.assertTrue(r["ok"], r)
        old, new = db.permit(self.pid), db.permit(r["new_id"])
        self.assertEqual((old["status"], old["replaced_by_id"]), ("renewed", new["id"]))
        self.assertEqual((new["status"], new["replaces_id"], new["source"]), ("active", self.pid, "renewal"))
        self.assertEqual((new["end_date"], new["permit_no"], new["listing_id"]), ("2027-10-05", "5009", 501))
        t = db.ticket(self.t["id"])
        self.assertEqual((t["state"], t["close_kind"]), ("closed", "renewed"))
        self.tick(at("2026-10-01", 10, 5))
        ch = self.port.channels[self.t["channel_id"]]
        self.assertTrue(ch["name"].startswith("مغلقة-"))
        self.assertTrue(ch["locked"])
        self.assertFalse(ch["buttons"])
        self.assertIn("✅ تجدّد", ch["messages"][-1]["text"])
        self.assertEqual([p["id"] for p in db.chain(r["new_id"])], [r["new_id"], self.pid])
        self.assertIsNone(db.live_ticket(r["new_id"]))

    def test_new_date_not_after_old_is_refused(self):
        for bad in ("2026-10-05", "2026-10-01"):
            r = service.renew(self.pid, bad, "x", "2026-10-01", proof=True, via="discord")
            self.assertFalse(r["ok"])
            self.assertIn("بعد", r["error_ar"])
        self.assertEqual(db.permit(self.pid)["status"], "active")

    def test_a_past_date_is_refused(self):
        p2 = self.add("2026-09-01", permit_no="7")
        r = service.renew(p2, "2026-09-20", "x", "2026-10-01", proof=True, via="discord")
        self.assertFalse(r["ok"])
        self.assertIn("الماضي", r["error_ar"])

    def test_unreadable_date_is_refused(self):
        self.assertFalse(service.renew(self.pid, "قريب", "x", "2026-10-01", proof=True, via="discord")["ok"])

    def test_proof_is_required(self):
        r = service.renew(self.pid, "2027-10-05", "x", "2026-10-01", proof=False, via="discord")
        self.assertFalse(r["ok"])
        r = service.renew(self.pid, "2027-10-05", "x", "2026-10-01", via="dashboard")
        self.assertFalse(r["ok"])
        r = service.renew(self.pid, "2027-10-05", "x", "2026-10-01", via="dashboard",
                          override_reason="المستند عند المالك", is_admin=False)
        self.assertFalse(r["ok"])
        r = service.renew(self.pid, "2027-10-05", "x", "2026-10-01", via="dashboard",
                          override_reason="المستند عند المالك", is_admin=True)
        self.assertTrue(r["ok"], r)

    def test_dashboard_with_a_document(self):
        r = service.renew(self.pid, "2027-10-05", "x", "2026-10-01", via="dashboard", doc_path="permits_docs/1/a.pdf")
        self.assertTrue(r["ok"], r)
        self.assertEqual(db.permit(r["new_id"])["doc_path"], "permits_docs/1/a.pdf")


class CancelTest(Case):

    def test_refused_for_people_without_the_right(self):
        pid = self.add("2026-10-05")
        r = service.cancel(pid, "المالك باع الشقة", "x", allowed=False)
        self.assertFalse(r["ok"])
        self.assertEqual(db.permit(pid)["status"], "active")

    def test_reason_length(self):
        pid = self.add("2026-10-05")
        self.assertFalse(service.cancel(pid, "لا", "x", allowed=True)["ok"])
        self.assertFalse(service.cancel(pid, "ب" * 401, "x", allowed=True)["ok"])
        r = service.cancel(pid, "المالك باع الشقة", "x", allowed=True)
        self.assertTrue(r["ok"])
        self.assertEqual(db.permit(pid)["status"], "cancelled")

    def test_cancel_closes_the_live_ticket(self):
        pid = self.add("2026-10-05")
        self.live()
        self.tick(at("2026-10-01", 10))
        t = self.tickets()[0]
        service.cancel(pid, "المالك باع الشقة", "فيصل", allowed=True)
        self.assertEqual((db.ticket(t["id"])["state"], db.ticket(t["id"])["close_kind"]), ("closed", "cancelled"))
        self.tick(at("2026-10-01", 10, 5))
        self.assertTrue(self.port.channels[t["channel_id"]]["locked"])


class CorrectTest(Case):

    def setUp(self):
        super().setUp()
        self.pid = self.add("2026-10-05")
        self.live()
        self.tick(at("2026-10-01", 10))
        self.t = self.tickets()[0]

    def test_end_date_change_needs_a_reason(self):
        r = service.update(self.pid, {"end_date": "2026-12-05"}, "x", "2026-10-01")
        self.assertFalse(r["ok"])

    def test_outside_the_window_closes_as_corrected(self):
        r = service.update(self.pid, {"end_date": "2026-12-05"}, "x", "2026-10-01", reason="خطأ طباعة بالسنة")
        self.assertTrue(r["ok"], r)
        t = db.ticket(self.t["id"])
        self.assertEqual((t["state"], t["close_kind"]), ("closed", "corrected"))
        self.tick(at("2026-10-01", 10, 5))
        self.assertIn("✏️ تصحيح", self.port.channels[self.t["channel_id"]]["messages"][-1]["text"])

    def test_inside_the_window_the_ticket_stays(self):
        service.update(self.pid, {"end_date": "2026-10-07"}, "x", "2026-10-01", reason="اليوم غلط")
        self.assertEqual(db.ticket(self.t["id"])["state"], "open")

    def test_other_fields_need_no_reason(self):
        r = service.update(self.pid, {"notes": "اتصلنا بالمالك"}, "x", "2026-10-01")
        self.assertTrue(r["ok"])
        self.assertEqual(db.permit(self.pid)["notes"], "اتصلنا بالمالك")


if __name__ == "__main__":
    unittest.main()
