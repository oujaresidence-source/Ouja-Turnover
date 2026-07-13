# -*- coding: utf-8 -*-
"""
Thin, import-safe bridge to the FROZEN renderer in owner_report/renderer/.

Two reasons this shim exists:
  1. The renderer uses Python-3.12+ syntax and pulls in Playwright, so importing it must
     be LAZY — pure-logic modules and their tests must import fine on older Pythons.
  2. audit_layout needs the report HTML, but render_report emits a PDF. The renderer
     writes the assembled HTML to "<out_dir>/_report.html" as a side effect just before
     printing, so we read it back to run the layout audit on the exact rendered markup.

We never modify the renderer. REPORT_SCHEMA_KEYS is duplicated here as a plain literal
(kept in sync with, and asserted against, the renderer's REPORT_SCHEMA) so validation and
tests can run without importing the renderer.
"""
from __future__ import annotations

import pathlib
import sys

_RENDERER_DIR = pathlib.Path(__file__).parent / "renderer"

# Mirror of ouja_render.REPORT_SCHEMA. verify_schema_matches() proves it stays in sync.
REPORT_SCHEMA_KEYS = [
    "UNIT", "OWNER", "REPORT", "ASSET", "MARKET_YIELD", "RENT_FREEZE",
    "EJAR", "MONTHS", "COSTS", "FURNISHING", "CHANNELS", "BOOKING_BEHAVIOUR",
    "COMP_SET", "GUEST", "FACTORS", "RISKS", "PROJECTION", "ACTIONS", "SOURCES",
]


def _ensure_path():
    p = str(_RENDERER_DIR.resolve())
    if p not in sys.path:
        sys.path.insert(0, p)


def _load_renderer():
    _ensure_path()
    import ouja_render  # noqa: E402  (lazy, 3.12+ only)
    return ouja_render


def _load_audit():
    _ensure_path()
    import audit_layout  # noqa: E402
    return audit_layout


def verify_schema_matches() -> bool:
    """True iff our literal key list equals the frozen renderer's REPORT_SCHEMA."""
    return list(_load_renderer().REPORT_SCHEMA) == REPORT_SCHEMA_KEYS


def render(cfg: dict, out_path) -> pathlib.Path:
    """Render the 17-page PDF. Returns the PDF path. Also leaves _report.html alongside."""
    return _load_renderer().render_report(cfg, out_path)


def html_for(out_path) -> str:
    """Read the HTML the renderer wrote next to the PDF."""
    html = pathlib.Path(out_path).parent / "_report.html"
    return html.read_text(encoding="utf-8")


def assert_layout_clean(html: str) -> None:
    """spec §4 hard gate — raises RuntimeError on any overflow/clip violation."""
    _load_audit().assert_clean(html)


def audit_violations(html: str) -> list:
    return _load_audit().audit_html(html)
