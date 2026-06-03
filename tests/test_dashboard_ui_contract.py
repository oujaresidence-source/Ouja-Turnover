import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOT = ROOT / "bot.py"


def dashboard_html() -> str:
    text = BOT.read_text(encoding="utf-8")
    start = text.index('DASHBOARD_HTML = """')
    start = text.index('"""', start) + 3
    end = text.index('"""', start)
    return text[start:end]


class DashboardUiContractTest(unittest.TestCase):
    def test_shared_dashboard_ui_contract_is_present(self):
        html = dashboard_html()

        self.assertIn("unicode-bidi:isolate", html)
        self.assertIn("overflow-wrap:anywhere", html)
        self.assertIn("function badgeInfo", html)
        self.assertIn(".badge.danger", html)
        self.assertIn(".badge.warn", html)
        self.assertIn("data-empty-title", html)
        self.assertIn("aria-busy", html)
        self.assertIn("approveBulkSummary", html)
        self.assertIn("confirmDanger", html)


if __name__ == "__main__":
    unittest.main()
