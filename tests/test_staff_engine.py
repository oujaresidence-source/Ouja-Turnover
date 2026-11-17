# -*- coding: utf-8 -*-
"""«عوجا فريق» — the pure engine that turns the team calendar + today's snapshot into ONE
employee's day. Every number here is synthetic."""

import unittest

from staff import engine


def _apt(i, name, owner, lid):
    return {"id": i, "name": name, "owner_id": owner, "listing_id": lid}


def _day():
    # نورة works and covers سارة (off). خالد works. سارة is off.
    return {
        "date": "2026-11-17", "weekday_ar": "الثلاثاء",
        "working": [
            {"id": 1, "name": "نورة", "emoji": "", "color": "#A57A2C",
             "own": [_apt(11, "Ouja | 12B", 1, 1012), _apt(12, "Ouja | A3", 1, 1013)],
             "coverage": [{"apartment": _apt(31, "Ouja | N06", 3, 1031), "owner_id": 3,
                           "owner_name": "سارة", "overridden": False}],
             "load": 3},
            {"id": 2, "name": "خالد", "emoji": "", "color": "#2E6A49",
             "own": [_apt(21, "Ouja | D20", 2, 1021)], "coverage": [], "load": 1},
        ],
        "off": [
            {"id": 3, "name": "سارة", "emoji": "", "color": "", "reason": "leave",
             "apartments": [{"apartment": _apt(31, "Ouja | N06", 3, 1031),
                             "covering_id": 1, "covering_name": "نورة"}]},
        ],
    }


def _snap():
    return {
        "date": "2026-11-17",
        "arrivals": [{"guest": "Fahad Alqahtani", "unit": "Ouja | 12B", "nights": 3,
                      "checkout": "2026-11-20"},
                     {"guest": "Mona Saleh", "unit": "Ouja | N06", "nights": 1,
                      "checkout": "2026-11-18"}],
        "departures": [{"guest": "Ali", "unit": "Ouja | 12B"},
                       {"guest": "Reem", "unit": "Ouja | A3"}],
        "empty": [{"unit": "Ouja | D20", "lid": 1021}],
        "arr_tickets": [],
    }


NAMES = {"Ouja | 12B": 1012, "Ouja | A3": 1013, "Ouja | N06": 1031, "Ouja | D20": 1021}


def build(emp="نورة", **kw):
    args = dict(employee=emp, day=_day(), snap=_snap(), tickets=[], promises=[], cleaning={},
                oncall={}, today_iso="2026-11-17", now_iso="2026-11-17T10:00:00",
                name_to_lid=NAMES)
    args.update(kw)
    return engine.build_today(**args)


class FirstName(unittest.TestCase):
    def test_first_word_only(self):
        self.assertEqual(engine.first_name("Fahad Alqahtani"), "Fahad")

    def test_blank(self):
        self.assertEqual(engine.first_name("  "), "")
        self.assertEqual(engine.first_name(None), "")


class Status(unittest.TestCase):
    def test_working_with_coverage(self):
        r = build()
        self.assertEqual(r["status"], "working")
        self.assertEqual(r["covering_for"], ["سارة"])
        lids = [a["lid"] for a in r["apartments"]]
        self.assertEqual(sorted(lids), [1012, 1013, 1031])
        cov = [a for a in r["apartments"] if not a["mine"]]
        self.assertEqual([a["owner_name"] for a in cov], ["سارة"])

    def test_off_lists_who_covers(self):
        r = build("سارة")
        self.assertEqual(r["status"], "leave")
        self.assertEqual(r["apartments"], [])
        self.assertEqual(r["covered_by"], [{"name": "Ouja | N06", "by": "نورة"}])

    def test_unknown_employee(self):
        r = build("مجهول")
        self.assertEqual(r["status"], "unknown")
        self.assertEqual(r["apartments"], [])

    def test_never_states_counts(self):
        # owner rule: no apartment counts anywhere — the payload carries no total/load fields
        r = build()
        flat = repr(r)
        for k in ("'total'", "'load'", "'count'", "'n'"):
            self.assertNotIn(k, flat)


class Events(unittest.TestCase):
    def test_turnover_checkout_checkin_vacant(self):
        ev = {a["lid"]: a["event"] for a in build("نورة")["apartments"]}
        self.assertEqual(ev[1012], "turnover")
        self.assertEqual(ev[1013], "checkout")
        self.assertEqual(ev[1031], "checkin")
        ev2 = {a["lid"]: a["event"] for a in build("خالد")["apartments"]}
        self.assertEqual(ev2[1021], "vacant")

    def test_inhouse_when_not_empty_and_no_movement(self):
        snap = _snap()
        snap["empty"] = []
        ev = {a["lid"]: a["event"] for a in build("خالد", snap=snap)["apartments"]}
        self.assertEqual(ev[1021], "inhouse")

    def test_unknown_without_snapshot(self):
        ev = {a["lid"]: a["event"] for a in build(snap={})["apartments"]}
        self.assertEqual(set(ev.values()), {"unknown"})

    def test_guest_first_name_only(self):
        a = [x for x in build()["apartments"] if x["lid"] == 1012][0]
        self.assertEqual(a["guest"], "Fahad")
        self.assertNotIn("Alqahtani", repr(build()))


class Cleaning(unittest.TestCase):
    def test_states(self):
        f = engine.cleaning_state
        self.assertEqual(f("", "")["key"], "none")
        self.assertEqual(f("", "arrived")["key"], "arrived")
        self.assertEqual(f("", "started")["key"], "cleaning")
        self.assertEqual(f("", "done")["key"], "done")
        self.assertEqual(f("submitted_for_review", "done")["key"], "review")
        self.assertEqual(f("approved", "")["key"], "approved")
        self.assertEqual(f("needs_reshoot", "done")["key"], "reshoot")
        self.assertEqual(f("issue_found", "")["key"], "issue")
        self.assertEqual(f("draft", "")["key"], "none")

    def test_report_beats_route_ping(self):
        c = {1012: {"report": "approved", "action": "started"}}
        a = [x for x in build(cleaning=c)["apartments"] if x["lid"] == 1012][0]
        self.assertEqual(a["cleaning"]["key"], "approved")


class NextThings(unittest.TestCase):
    def test_turnover_not_cleaned_is_first(self):
        r = build()
        self.assertEqual(r["next"][0]["lid"], 1012)
        self.assertEqual(r["next"][0]["kind"], "turnover_clean")
        self.assertLessEqual(len(r["next"]), 3)

    def test_arrival_with_open_ticket_outranks_everything(self):
        t = [{"id": "tk1", "lid": 1031, "status": "open", "priority": "med", "title": "مكيف",
              "due_date": None}]
        r = build(tickets=t)
        self.assertEqual(r["next"][0]["kind"], "arrival_ticket")
        self.assertEqual(r["next"][0]["lid"], 1031)

    def test_cleaned_turnover_drops_out(self):
        c = {1012: {"report": "approved", "action": "done"},
             1013: {"report": "approved", "action": "done"}}
        kinds = [x["kind"] for x in build(cleaning=c)["tasks"]]
        self.assertNotIn("turnover_clean", kinds)
        self.assertNotIn("checkout_clean", kinds)
        self.assertIn("checkin", kinds)

    def test_only_my_tickets_and_promises(self):
        t = [{"id": "a", "lid": 1021, "status": "open", "priority": "urgent", "title": "x",
              "due_date": None},
             {"id": "b", "lid": 1013, "status": "open", "priority": "low", "title": "y",
              "due_date": None},
             {"id": "c", "lid": 1013, "status": "fixed", "priority": "urgent", "title": "z",
              "due_date": None}]
        p = [{"id": "p1", "listing_id": "1021", "status": "open", "promise_text": "مناشف",
              "due_at": "2026-11-17T09:00:00"},
             {"id": "p2", "listing_id": "1031", "status": "open", "promise_text": "مخدة",
              "due_at": "2026-11-17T09:00:00"}]
        r = build(tickets=t, promises=p)
        refs = {x.get("ref") for x in r["tasks"]}
        self.assertIn("b", refs)
        self.assertIn("p2", refs)
        self.assertNotIn("a", refs)          # خالد's apartment
        self.assertNotIn("p1", refs)
        self.assertNotIn("c", refs)          # fixed

    def test_overdue_promise_is_danger(self):
        p = [{"id": "p2", "listing_id": "1031", "status": "open", "promise_text": "مخدة",
              "due_at": "2026-11-17T09:00:00"}]
        x = [t for t in build(promises=p)["tasks"] if t.get("ref") == "p2"][0]
        self.assertEqual(x["kind"], "promise_late")
        self.assertEqual(x["tone"], "danger")

    def test_overdue_ticket_by_due_date(self):
        t = [{"id": "b", "lid": 1013, "status": "in_progress", "priority": "low", "title": "y",
              "due_date": "2026-11-16"}]
        x = [k for k in build(tickets=t)["tasks"] if k.get("ref") == "b"][0]
        self.assertEqual(x["kind"], "ticket_late")


class Team(unittest.TestCase):
    def test_team_lists_without_counts(self):
        tm = build()["team"]
        self.assertEqual([w["name"] for w in tm["working"]], ["نورة", "خالد"])
        self.assertEqual(tm["working"][0]["covering_for"], ["سارة"])
        self.assertEqual(tm["off"][0]["name"], "سارة")
        self.assertEqual(tm["off"][0]["covered_by"], ["نورة"])
        self.assertTrue(tm["working"][0]["me"])

    def test_oncall_passthrough(self):
        oc = {"now": None, "tonight": [{"employee": "خالد", "from": "22:00", "to": "02:00"}]}
        self.assertEqual(build(oncall=oc)["oncall"]["tonight"][0]["employee"], "خالد")


class Supervisor(unittest.TestCase):
    def test_review_items(self):
        rows = [{"lid": 1013, "name": "Ouja | A3", "status": "submitted_for_review"},
                {"lid": 1021, "name": "Ouja | D20", "status": "approved"}]
        items = engine.supervisor_items(rows, replies=2, escalations=1)
        kinds = [i["kind"] for i in items]
        self.assertEqual(kinds.count("review"), 1)
        self.assertIn("replies", kinds)
        self.assertIn("escalations", kinds)

    def test_nothing_waiting(self):
        self.assertEqual(engine.supervisor_items([], 0, 0), [])



class Week(unittest.TestCase):
    def test_week_statuses(self):
        d1 = _day()
        d2 = dict(_day(), date="2026-11-18", weekday_ar="الأربعاء")
        w = engine.my_week([d1, d2], "سارة")
        self.assertEqual([x["status"] for x in w], ["leave", "leave"])
        self.assertEqual(engine.my_week([d1], "نورة")[0]["status"], "working")


if __name__ == "__main__":
    unittest.main()
