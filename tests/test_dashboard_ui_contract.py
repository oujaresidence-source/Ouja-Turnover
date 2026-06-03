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

    def test_full_operations_ui_pass_contract_is_present(self):
        html = dashboard_html()

        for css_class in [
            ".ops-strip",
            ".ops-card",
            ".risk-panel",
            ".action-bar",
            ".data-empty",
            ".status-rail",
        ]:
            self.assertIn(css_class, html)

        for helper in [
            "function emptyState",
            "function opsStrip",
            "function riskPanel",
            "function setBusy",
            "function confirmAction",
            "function bulkPriceSummary",
            "function pricingApplySummary",
        ]:
            self.assertIn(helper, html)

        for page_hook in [
            "homeCommandDeck",
            "inboxOpsSummary",
            "calendarOpsSummary",
            "pricingOpsSummary",
            "strategiesOpsSummary",
            "cleaningOpsSummary",
            "listingsOpsSummary",
            "qualityOpsSummary",
            "guestsOpsSummary",
            "ticketsOpsSummary",
            "designOpsSummary",
            "pmoOpsSummary",
            "revenueOpsSummary",
            "expensesOpsSummary",
            "financeOpsSummary",
        ]:
            self.assertIn(page_hook, html)

        self.assertIn("renderAllPageOps", html)

    def test_expenses_v2_dashboard_contract_is_present(self):
        html = dashboard_html()

        for text in [
            "المصاريف V2",
            "تحليل المصادر الثلاثة",
            "مطابقة وإصلاح",
            "لا تعرض علامة الصح إلا بعد التحقق من Hostaway",
            "Download diagnostics CSV",
        ]:
            self.assertIn(text, html)

        for helper in [
            "function expV2Reconcile",
            "function expV2RepairPlan",
            "function expV2Split",
            "function expV2DiagnosticsHtml",
            "/api/expenses/v2/overview",
            "/api/expenses/v2/repair-apply",
            "/api/expenses/v2/split-confirm",
        ]:
            self.assertIn(helper, html)


class ProductBriefContractTest(unittest.TestCase):
    def test_product_brief_exists_for_design_work(self):
        product = ROOT / "PRODUCT.md"
        self.assertTrue(product.exists())
        text = product.read_text(encoding="utf-8")
        self.assertIn("## Register\n\nproduct", text)
        self.assertIn("Ouja Residence operators", text)


if __name__ == "__main__":
    unittest.main()
