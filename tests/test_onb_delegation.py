# -*- coding: utf-8 -*-
"""
Delegation, the ticket it opens, and the link that ticket carries.

Three promises are guarded here, because all three are invisible until they break:
  * ONE save produces ONE ticket per person — never eight pings, never a silent none.
  * notified_at is a LEDGER: stamped only after Discord accepted, so an outage retries
    instead of swallowing the announcement.
  * A token is scoped to ONE person on ONE project, and the page it opens carries no client
    contact details — an unauthenticated link gets forwarded around.

Run: python3 -m unittest tests.test_onb_delegation
"""

import inspect
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from onboarding import catalogue, db, engine, routes                       # noqa: E402
from tests.test_onb_harness import (_Req, body, boot, make_ready,          # noqa: E402
                                    READY, run)


class DelegationCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rec = boot("onbdeleg_")

    def setUp(self):
        self.rec.reset()

    def mk(self, people=(1, 2), **over):
        f = dict(READY)
        f.update(over)
        p = body(run(routes.api_create(_Req(f))))["project"]
        for eid in people:
            r = body(run(routes.api_assignee_add(_Req({"project_id": p["id"],
                                                       "employee_id": eid}))))
            self.assertTrue(r["ok"], r)
        return p

    def keys(self, pid, wanted):
        return [t for t in db.tasks(pid) if t["catalogue_key"] in wanted]

    def assign(self, pid, pairs):
        """pairs: [(catalogue_key, employee_id or None)]"""
        rows = {t["catalogue_key"]: t for t in db.tasks(pid)}
        ch = [{"task_id": rows[k]["id"], "employee_id": e} for k, e in pairs]
        return body(run(routes.task_assign(_Req({"project_id": pid, "changes": ch}))))


class TestAnyTaskAnyPerson(DelegationCase):

    def test_25_a_role_label_never_blocks_an_assignment(self):
        """Build spec R7. The owner decides who does what, not the catalogue."""
        p = self.mk()
        am = [r[0] for r in catalogue.CATALOGUE if r[4] == "am" and r[1] != "ongoing"][0]
        ceo = [r[0] for r in catalogue.CATALOGUE if r[4] == "ceo" and r[1] != "ongoing"][0]
        r = self.assign(p["id"], [(am, 1), (ceo, 1)])
        self.assertTrue(r["ok"], r)
        for k in (am, ceo):
            self.assertEqual(self.keys(p["id"], {k})[0]["assignee_name"], "ناصر")

    def test_25b_the_restriction_cannot_creep_back_in(self):
        src = inspect.getsource(routes.task_assign)
        self.assertNotIn("owner_role", src,
                         "task_assign started consulting owner_role — R7 is broken")


class TestOneSaveOneTicket(DelegationCase):

    def test_26_eight_tasks_to_one_person_is_one_payload(self):
        p = self.mk()
        keys = [r[0] for r in catalogue.rows_for_seed()][:8]
        r = self.assign(p["id"], [(k, 1) for k in keys])
        self.assertTrue(r["ok"], r)
        self.assertEqual(len(self.rec.payloads), 1,
                         "one save produced %d pings" % len(self.rec.payloads))
        text = self.rec.payloads[0]["text"]
        rows = {t["catalogue_key"]: t for t in db.tasks(p["id"])}
        for k in keys:
            self.assertIn(rows[k]["title_ar"], text, "%s missing from the card" % k)
        self.assertEqual(text.count("https://ouja.test/onb/t/"), 1, "more than one link")
        self.assertEqual(r["notified"][0]["count"], 8)

    def test_27_a_batch_touching_both_people_emits_exactly_two(self):
        p = self.mk()
        keys = [r[0] for r in catalogue.rows_for_seed()][:6]
        r = self.assign(p["id"], [(keys[0], 1), (keys[1], 1), (keys[2], 1),
                                  (keys[3], 2), (keys[4], 2), (keys[5], 2)])
        self.assertTrue(r["ok"], r)
        self.assertEqual(len(self.rec.payloads), 2)
        by_name = {pl["employee_name"]: pl for pl in self.rec.payloads}
        self.assertEqual(set(by_name), {"ناصر", "نورة"})
        rows = {t["catalogue_key"]: t for t in db.tasks(p["id"])}
        self.assertIn(rows[keys[0]]["title_ar"], by_name["ناصر"]["text"])
        self.assertNotIn(rows[keys[0]]["title_ar"], by_name["نورة"]["text"])

    def test_28_re_saving_an_unchanged_assignment_pings_nobody(self):
        p = self.mk()
        keys = [r[0] for r in catalogue.rows_for_seed()][:3]
        self.assign(p["id"], [(k, 1) for k in keys])
        self.assertEqual(len(self.rec.payloads), 1)
        self.assign(p["id"], [(k, 1) for k in keys])
        self.assertEqual(len(self.rec.payloads), 1, "the second save pinged again")

    def test_29_moving_a_task_re_pings_the_new_person_only(self):
        p = self.mk()
        k = catalogue.rows_for_seed()[0][0]
        self.assign(p["id"], [(k, 1)])
        self.rec.reset()
        self.assign(p["id"], [(k, 2)])
        self.assertEqual(len(self.rec.payloads), 1)
        self.assertEqual(self.rec.payloads[0]["employee_name"], "نورة")
        self.assertEqual(self.keys(p["id"], {k})[0]["assignee_name"], "نورة")

    def test_30_an_unreachable_person_still_gets_a_visible_card(self):
        """عهود has no Discord id. A silent skip would hide the hole; a broken mention would
        look like a bug. The plain name keeps the gap visible."""
        p = self.mk(people=(3,))
        k = catalogue.rows_for_seed()[0][0]
        r = self.assign(p["id"], [(k, 3)])
        self.assertTrue(r["ok"], r)
        self.assertEqual(len(self.rec.payloads), 1)
        text = self.rec.payloads[0]["text"]
        self.assertIn("عهود", text)
        self.assertNotIn("<@", text)
        self.assertFalse(r["notified"][0]["reachable"])

    def test_31_a_failing_notify_writes_the_work_but_never_the_stamp(self):
        p = self.mk()
        k = catalogue.rows_for_seed()[0][0]
        self.rec.fail = True
        r = self.assign(p["id"], [(k, 1)])
        self.assertTrue(r["ok"], "a Discord outage must not refuse the assignment")
        row = self.keys(p["id"], {k})[0]
        self.assertEqual(row["assignee_name"], "ناصر", "the assignment was lost")
        self.assertIsNone(row["notified_at"], "stamped despite a failed send")
        self.assertFalse(r["notified"][0]["sent"])
        # the next save retries the ping
        self.rec.fail = False
        self.assign(p["id"], [(k, 1)])
        self.assertEqual(len(self.rec.payloads), 1, "the retry never happened")
        self.assertIsNotNone(self.keys(p["id"], {k})[0]["notified_at"])


class TestCard(DelegationCase):

    def test_32_the_card_groups_by_stage_locks_gates_and_carries_no_backslash(self):
        p = {"unit_name": "Ouja | الملقا 1", "ref": "OJ-ONB-0007",
             "client_name": "عبدالله", "district": "الملقا", "handover_target": "2026-09-20"}
        emp = {"employee_name": "نورة", "employee_did": "2222"}
        tasks = [
            {"stage": "photoshoot", "seq": 2, "title_ar": "طلب تنظيف عميق", "gate": 1,
             "catalogue_key": "s6.2"},
            {"stage": "license", "seq": 3, "title_ar": "تركيب معدات السلامة وتصويرها", "gate": 1,
             "catalogue_key": "s5.3"},
            {"stage": "license", "seq": 4, "title_ar": "تجميع مستندات الرخصة من العميل", "gate": 0,
             "catalogue_key": "s5.4"},
        ]
        link = "https://ouja.test/onb/t/abc123"
        text = engine.assignment_card(p, emp, tasks, link)
        self.assertNotIn(chr(92), text, "a backslash reached the Discord card")
        self.assertIn(link, text)
        self.assertIn("<@2222>", text)
        # license (stage 5) is announced before photoshoot (stage 6), whatever order they arrived
        self.assertLess(text.index("تركيب معدات السلامة"), text.index("طلب تنظيف عميق"))
        self.assertIn("🔒 تركيب معدات السلامة وتصويرها", text)
        self.assertIn("  تجميع مستندات الرخصة من العميل", text)
        self.assertNotIn("🔒 تجميع مستندات", text)

    def test_32b_a_long_batch_is_truncated_and_says_so(self):
        p = {"unit_name": "u", "ref": "r"}
        emp = {"employee_name": "ناصر", "employee_did": ""}
        tasks = [{"stage": "lead", "seq": i, "title_ar": "مهمة رقم %d" % i, "gate": 0,
                  "catalogue_key": "s1.%d" % i} for i in range(1, 20)]
        text = engine.assignment_card(p, emp, tasks, "L")
        self.assertIn("مهمة رقم 12", text)
        self.assertNotIn("مهمة رقم 13", text)
        self.assertIn("و7 مهمة ثانية", text)


class TestTokenLink(DelegationCase):

    def _tok(self, pid, eid):
        return db.assignee(pid, eid)["access_token"]

    def test_33_a_token_shows_only_that_person_tasks(self):
        p = self.mk()
        keys = [r[0] for r in catalogue.rows_for_seed()][:4]
        self.assign(p["id"], [(keys[0], 1), (keys[1], 1), (keys[2], 2), (keys[3], 2)])
        a = body(run(routes.api_token_get(_Req(match={"token": self._tok(p["id"], 1)}))))
        b = body(run(routes.api_token_get(_Req(match={"token": self._tok(p["id"], 2)}))))
        self.assertTrue(a["ok"] and b["ok"])
        ka = {t["catalogue_key"] for t in a["tasks"]}
        kb = {t["catalogue_key"] for t in b["tasks"]}
        self.assertEqual(ka, {keys[0], keys[1]})
        self.assertEqual(kb, {keys[2], keys[3]})
        self.assertEqual(ka & kb, set(), "the two token views overlap")
        self.assertEqual(a["buddy"], "نورة")

    def test_34_a_token_cannot_touch_the_other_person_task(self):
        p = self.mk()
        keys = [r[0] for r in catalogue.rows_for_seed()][:2]
        self.assign(p["id"], [(keys[0], 1), (keys[1], 2)])
        hers = self.keys(p["id"], {keys[1]})[0]
        r = body(run(routes.api_token_submit(_Req({"token": self._tok(p["id"], 1),
                                                   "task_id": hers["id"],
                                                   "resolution": "done"}))))
        self.assertFalse(r["ok"])
        self.assertEqual(db.task(hers["id"])["resolution"], "open", "it wrote anyway")

    def test_35_a_token_cannot_reach_another_project(self):
        p1 = self.mk()
        p2 = self.mk()
        k = catalogue.rows_for_seed()[0][0]
        self.assign(p1["id"], [(k, 1)])
        self.assign(p2["id"], [(k, 1)])
        other = self.keys(p2["id"], {k})[0]
        r = body(run(routes.api_token_submit(_Req({"token": self._tok(p1["id"], 1),
                                                   "task_id": other["id"],
                                                   "resolution": "done"}))))
        self.assertFalse(r["ok"])
        self.assertEqual(db.task(other["id"])["resolution"], "open")

    def test_36_the_link_never_carries_the_client_contact_details(self):
        """An unauthenticated link gets forwarded around. By key AND by value."""
        p = self.mk()
        run(routes.api_update(_Req({"id": p["id"], "client_email": "secret@client.com"})))
        k = catalogue.rows_for_seed()[0][0]
        self.assign(p["id"], [(k, 1)])
        resp = body(run(routes.api_token_get(_Req(match={"token": self._tok(p["id"], 1)}))))
        blob = json.dumps(resp, ensure_ascii=False)
        for key in ("client_whatsapp", "client_email"):
            self.assertNotIn(key, blob, "%s key leaked to the public link" % key)
        for val in ("0555000000", "secret@client.com"):
            self.assertNotIn(val, blob, "%s value leaked to the public link" % val)
        self.assertEqual(resp["project"]["client_name"], "عبدالله الشمري")

    def test_37_an_unknown_token_is_an_answer_not_a_crash(self):
        r = run(routes.api_token_get(_Req(match={"token": "nope-nope-nope"})))
        self.assertEqual(r["status"], 200)
        self.assertFalse(r["data"]["ok"])
        self.assertIn("ما عاد شغّال", r["data"]["error"])
        w = run(routes.api_token_submit(_Req({"token": "nope", "task_id": 1,
                                              "resolution": "done"})))
        self.assertEqual(w["status"], 200)
        self.assertFalse(w["data"]["ok"])

    def test_38_after_publish_the_link_is_read_only(self):
        p = self.mk()
        k = catalogue.rows_for_seed()[0][0]
        self.assign(p["id"], [(k, 1)])
        mine = self.keys(p["id"], {k})[0]
        make_ready(routes, p["id"], people=())
        self.assertTrue(body(run(routes.publish(_Req({"id": p["id"]}))))["ok"])
        view = body(run(routes.api_token_get(_Req(match={"token": self._tok(p["id"], 1)}))))
        self.assertTrue(view["readonly"])
        r = body(run(routes.api_token_submit(_Req({"token": self._tok(p["id"], 1),
                                                   "task_id": mine["id"],
                                                   "resolution": "blocked",
                                                   "reason": "متأخر"}))))
        self.assertFalse(r["ok"])
        self.assertIn("انسلّمت", r["error"])

    def test_38b_the_employee_may_not_resolve_without_a_reason_either(self):
        p = self.mk()
        k = catalogue.rows_for_seed()[0][0]
        self.assign(p["id"], [(k, 1)])
        mine = self.keys(p["id"], {k})[0]
        r = body(run(routes.api_token_submit(_Req({"token": self._tok(p["id"], 1),
                                                   "task_id": mine["id"],
                                                   "resolution": "na", "reason": " "}))))
        self.assertFalse(r["ok"])
        ok = body(run(routes.api_token_submit(_Req({"token": self._tok(p["id"], 1),
                                                    "task_id": mine["id"],
                                                    "resolution": "done"}))))
        self.assertTrue(ok["ok"], ok)
        self.assertIn("(رابط)", db.task(mine["id"])["resolved_by"])


if __name__ == "__main__":
    unittest.main()
