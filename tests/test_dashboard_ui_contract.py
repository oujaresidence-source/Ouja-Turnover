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
        ]:
            self.assertIn(page_hook, html)

        self.assertIn("renderAllPageOps", html)

    def test_erp_v2_cutover_contract(self):
        """Slice 8: the old finance views are demolished; their sidebar ids
        redirect into the ERP v2 app (finance/ package) instead."""
        html = dashboard_html()

        # condemned views are GONE from the dashboard
        for dead in ['id="view_fb"', 'id="view_finance"', 'id="view_expenses"',
                     "function loadFb(", "function loadFinance(", "function loadExpenses(",
                     "function openBulkPdf(", "function financeGeneratePdf("]:
            self.assertNotIn(dead, html)

        # the cutover redirect handles erp/fb/finance/expenses ids in go()
        self.assertIn("old finance views are cut over to ERP v2", html)
        for tk in ["erp:'", "fb:'", "finance:'", "expenses:'"]:
            self.assertIn(tk, html)        # labels stay (entries redirect)

        # shared helpers that other views still use survived the demolition
        for kept in ["function fbCard()", "function fbChip(", "function fbInp()",
                     "function fbStatCard(", "function fbModal("]:
            self.assertIn(kept, html)

        # the new system actually exists and mounts the core routes
        erp = (ROOT / "finance" / "__init__.py").read_text(encoding="utf-8")
        for route in ["/erp", "/erp/version", "/erp/api/work-queue", "/erp/api/bank",
                      "/erp/api/match", "/erp/api/stmts", "/erp/api/close",
                      "/erp/api/budget", "/fin/receipt/{expense_id}"]:
            self.assertIn('"' + route + '"', erp)
        bot_text = BOT.read_text(encoding="utf-8")
        self.assertIn("_finance_erp.mount(app", bot_text)


class ProductBriefContractTest(unittest.TestCase):
    def test_product_brief_exists_for_design_work(self):
        product = ROOT / "PRODUCT.md"
        self.assertTrue(product.exists())
        text = product.read_text(encoding="utf-8")
        self.assertIn("## Register\n\nproduct", text)
        self.assertIn("Ouja Residence operators", text)


if __name__ == "__main__":
    unittest.main()
