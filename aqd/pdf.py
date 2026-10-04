# -*- coding: utf-8 -*-
"""
aqd.pdf — HTML → PDF on the ONE shared Chromium (owner_report.renderer.ouja_render): the work is
submitted to its single-thread `_pw_pool` and printed by `_pw_print`, so the container never runs
a second browser and renders stay serialised.

Signing is NEVER blocked by a PDF: if Playwright is missing or Chromium fails, to_pdf() returns
False, the HTML is kept next to where the PDF would be, and downloads serve that HTML instead.
The template's own @page margins win over _pw_print's zero margins (Chromium honours CSS @page).
"""

import os
import traceback

PDF_TIMEOUT_S = 120


def _renderer():
    try:
        from owner_report.renderer import ouja_render as r
        return r
    except Exception as e:                      # playwright not installed / import error
        print("[aqd] pdf renderer unavailable (HTML fallback):", e)
        return None


def to_pdf(html_text, pdf_path):
    """Write html_text beside pdf_path and print it. -> True when the PDF exists."""
    import pathlib
    pdf_path = pathlib.Path(pdf_path)
    html_tmp = pdf_path.with_suffix(".html")
    html_tmp.write_text(html_text, encoding="utf-8")
    if os.environ.get("AQD_PDF_DISABLED") == "1":
        return False
    r = _renderer()
    if r is None:
        return False
    try:
        r._pw_pool.submit(r._pw_print, html_tmp, pdf_path).result(timeout=PDF_TIMEOUT_S)
        return pdf_path.is_file() and pdf_path.stat().st_size > 0
    except Exception:
        traceback.print_exc()
        try:
            r._pw_state["browser"] = None       # a wedged Chromium is dropped, next call relaunches
        except Exception:
            pass
        return False
