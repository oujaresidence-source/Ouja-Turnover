# -*- coding: utf-8 -*-
"""
TDD lock for recovery.config — the two agents, and the conflict rule against the REAL book.

The failure this file exists to prevent is silent: if an agent's configured name stops
matching the Employee Calendar's owner name, conflict detection quietly stops working and
the person responsible for an apartment starts taking their own recovery calls. Nothing
raises. So the match is asserted here, against the calendar's own seed.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from recovery import config, engine  # noqa: E402
from schedule import seed  # noqa: E402


class TestAgentsAreRealCalendarPeople(unittest.TestCase):

    def test_both_agents_have_a_usable_discord_id(self):
        for a in config.AGENTS:
            self.assertTrue(a["id"].isdigit(), a)
            self.assertGreaterEqual(len(a["id"]), 17, a)   # a Discord snowflake

    def test_the_two_ids_are_not_the_same_person(self):
        self.assertNotEqual(config.AGENTS[0]["id"], config.AGENTS[1]["id"])

    def test_every_agent_name_exists_in_the_employee_calendar(self):
        """If this fails, conflict detection is dead and nothing tells you."""
        calendar_names = {e["name"] for e in seed.EMPLOYEES}
        for a in config.AGENTS:
            self.assertIn(a["name"], calendar_names,
                          "agent %r is not a name the calendar knows" % a["name"])

    def test_each_agent_actually_owns_apartments(self):
        # An agent who owns nothing can never be conflicted — worth knowing, because it
        # would make the whole conflict/equity machinery a no-op for them.
        for a in config.AGENTS:
            self.assertIn(a["name"], seed.APARTMENTS)
            self.assertGreater(len(seed.APARTMENTS[a["name"]]), 0)

    def test_lookup_helpers(self):
        self.assertTrue(config.is_agent("1514200235302195211"))
        self.assertFalse(config.is_agent("999"))
        self.assertEqual(config.agent_by_id("894222545274945548")["name"], "محمد اليامي")


class TestConflictAgainstTheRealBook(unittest.TestCase):
    """Drive the engine with the actual 53-apartment ownership map."""

    def owner_of(self, unit):
        for owner, units in seed.APARTMENTS.items():
            if unit in units:
                return owner
        return None

    def test_an_agent_never_calls_about_their_own_apartment(self):
        for a in config.AGENTS:
            unit = seed.APARTMENTS[a["name"]][0]
            pick = engine.choose_agent(config.AGENTS, {},
                                       unit_owner_name=self.owner_of(unit))
            self.assertNotEqual(pick["agent_id"], a["id"], unit)
            self.assertEqual(pick["excluded_id"], a["id"])

    def test_a_third_party_apartment_conflicts_with_nobody(self):
        # ناصر / مآثر / نورة are not recovery agents, so their units are free.
        unit_owner = "ناصر"
        pick = engine.choose_agent(config.AGENTS, {}, unit_owner_name=unit_owner)
        self.assertIsNone(pick["excluded_id"])
        self.assertEqual(pick["reason"], "equity")

    def test_both_agents_can_never_be_conflicted_by_ownership(self):
        """An apartment has exactly ONE owner, so the «both excluded» fallback in §4.4 can
        only ever be reached through leave/absence — never through a conflict. Worth
        pinning: it means the supervisor fallback is rare by construction."""
        for owner in seed.APARTMENTS:
            conflicted = engine.conflicted_agents(config.AGENTS, owner)
            self.assertLessEqual(len(conflicted), 1, owner)


class TestEquityOnTheRealOwnershipSplit(unittest.TestCase):
    """The ±2 target, simulated on the real book instead of a made-up one.

    عهود owns 10 of 53 apartments and محمد اليامي owns 11, so about 40% of tickets conflict
    with one of them and 60% are free — comfortably inside the range where equity repairs
    itself. This is the test that says the month-end gap alert should stay quiet in normal
    operation.
    """

    def _month(self, unit_sequence):
        stats = {}
        for unit in unit_sequence:
            owner = next((o for o, us in seed.APARTMENTS.items() if unit in us), None)
            pick = engine.choose_agent(config.AGENTS, stats, unit_owner_name=owner)
            if pick["excluded_id"]:
                stats = engine.apply_exclusion(stats, pick["excluded_id"])
            if pick["agent_id"]:
                stats = engine.apply_assignment(stats, pick["agent_id"], "2026-08-01")
        return stats

    def all_units(self):
        return [u for units in seed.APARTMENTS.values() for u in units]

    def test_a_month_of_tickets_spread_across_the_book_stays_within_two(self):
        units = self.all_units()
        # 60 tickets cycling through every apartment — a full, representative month.
        stats = self._month([units[i % len(units)] for i in range(60)])
        gap = engine.equity_gap(stats, config.agent_ids())
        self.assertLessEqual(gap, 2, "gap was %d" % gap)
        self.assertLess(gap, config.EQUITY_GAP_ALERT_THRESHOLD)   # alert stays quiet

    def test_the_worst_ordering_still_stays_within_two(self):
        # Every one of عهود's apartments first, then محمد's, then everyone else's —
        # the most hostile order the conflict rule can be handed.
        units = (list(seed.APARTMENTS["عهود"]) + list(seed.APARTMENTS["محمد اليامي"])
                 + list(seed.APARTMENTS["ناصر"]) + list(seed.APARTMENTS["مآثر"])
                 + list(seed.APARTMENTS["نورة"]))
        stats = self._month(units)
        gap = engine.equity_gap(stats, config.agent_ids())
        self.assertLessEqual(gap, 2, "gap was %d" % gap)

    def test_both_agents_actually_get_work(self):
        stats = self._month(self.all_units())
        for aid in config.agent_ids():
            self.assertGreater(stats.get(aid, {}).get("assigned_count", 0), 0)


class TestNotReadyToPostYet(unittest.TestCase):

    def test_the_feature_refuses_discord_until_the_roles_and_domain_are_set(self):
        ok, missing = config.ready_for_discord()
        self.assertFalse(ok)
        blob = " ".join(missing)
        self.assertIn("SUPERVISOR", blob)
        self.assertIn("OPS_LEAD", blob)
        self.assertIn("PUBLIC_BASE_URL", blob)

    def test_the_agent_ids_are_no_longer_among_the_missing(self):
        _, missing = config.ready_for_discord()
        self.assertFalse([m for m in missing if "agent" in m], missing)

    def test_it_ships_switched_off(self):
        self.assertTrue(config.DRYRUN)      # computes and logs, posts nothing


if __name__ == "__main__":
    unittest.main(verbosity=2)
