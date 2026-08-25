# -*- coding: utf-8 -*-
"""
Weekly report ↔ Employee Calendar contract (text-level, no bot import — same pattern as
test_dashboard_ui_contract). Locks the three linked features:
  1. auto-assign: template enrichment + save whitelist keep the `assignee` field,
  2. calendar delete: the Manage-tab delete button + confirm exist in the dashboard JS,
  3. weekly dropdown: employee select + auto-fill helpers exist and read /api/weekly/owners.

Run:  python3 -m unittest tests.test_weekly_assign_contract
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOT = ROOT / "bot.py"


def bot_text() -> str:
    return BOT.read_text(encoding="utf-8")


def dashboard_html() -> str:
    text = bot_text()
    start = text.index('DASHBOARD_HTML = """')
    start = text.index('"""', start) + 3
    end = text.index('"""', start)
    return text[start:end]


class WeeklyAssignContractTest(unittest.TestCase):
    def test_server_side_assignee_pipeline(self):
        text = bot_text()
        # single shared resolver (schedule.owners) feeds the weekly endpoints
        self.assertIn("_schedule.owners.permanent_map()", text)
        self.assertIn("def _weekly_perm_owners", text)
        self.assertIn("async def _api_weekly_owners", text)
        self.assertIn('add_get("/api/weekly/owners", _api_weekly_owners)', text)
        # the save whitelist must keep assignee (whitelisted dict — a missing key silently drops it)
        self.assertIn('"assignee":  (apt.get("assignee") or "").strip()[:60]', text)

    def test_dashboard_weekly_dropdown_and_autofill(self):
        html = dashboard_html()
        for marker in [
            "function _wrEmployeeField",     # dropdown built from calendar employees
            "function _wrEmployeeChanged",   # re-fill on selection (+ confirm on edits)
            "function _wrOwnedFor",          # employee -> permanently owned apartments
            "function _wrOwnerOf",           # apartment -> permanent owner (chip + manual add)
            "function _wrAnyEdits",          # discard-warning gate
            "/api/weekly/owners",            # calendar snapshot endpoint
        ]:
            self.assertIn(marker, html)
        # dropdown must still degrade to the free-text input when the calendar is empty
        self.assertIn("'<input id=\"wrF_employee\" value=\"'", html)

    def test_dashboard_calendar_delete_button(self):
        html = dashboard_html()
        self.assertIn("function schedDelApt", html)
        self.assertIn("schedDelApt('+a.id+')", html)                       # button on each card
        self.assertIn("rdelete('/api/schedule/apartment/'+aptId)", html)   # existing cascade endpoint
        # destructive → must confirm before deleting
        delete_fn = html[html.index("function schedDelApt"):]
        self.assertIn("confirm(", delete_fn[:delete_fn.index("rdelete(")])


if __name__ == "__main__":
    unittest.main()
