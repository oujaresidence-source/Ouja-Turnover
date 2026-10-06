# -*- coding: utf-8 -*-
"""
owner_meet.pdf — the owner's PDF: the same 16:9 chapters, one per 1280×720 page (brief P8).

Production prints on the SHARED Chromium (owner_report.renderer.ouja_render: `_pw_pool` + `_pw_browser`
under `_pw_lock`) with this package's own print function — the shared `_pw_print` is A4-only and is
not modified. That renderer needs Python ≥ 3.12 (Railway runs 3.13); where it cannot import (a local
3.9 dev machine) a private playwright launch does the same job for the layout audit.

ANY failure returns False: the caller serves the HTML link instead, and the meeting is never blocked.
Dates inside the pages are already Arabic words (render.texts) — an ISO date in Arabic PDF text is
reordered by bidi (the ownerbill lesson).
"""

import os
import traceback

from . import render

PDF_TIMEOUT_S = int(os.environ.get("OWNER_MEET_PDF_TIMEOUT_S", "120"))
FONT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fonts")


def _font_base():
    return "file://" + FONT_DIR + "/"


def _print_with(browser, html_tmp, pdf_path):
    pg = browser.new_page()
    try:
        pg.goto("file://" + os.path.abspath(html_tmp))
        pg.wait_for_timeout(900)
        pg.pdf(path=pdf_path, width="1280px", height="720px", print_background=True, prefer_css_page_size=True,
               margin={"top": "0", "bottom": "0", "left": "0", "right": "0"})
    finally:
        try:
            pg.close()
        except Exception:
            pass


def _shared_print(html_tmp, pdf_path):
    """Runs ON the shared pool thread: the shared browser, under the shared lock."""
    from owner_report.renderer import ouja_render as r
    with r._pw_lock:
        _print_with(r._pw_browser(), html_tmp, pdf_path)


def _local_print(html_tmp, pdf_path):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(args=["--disable-dev-shm-usage"])
        try:
            _print_with(b, html_tmp, pdf_path)
        finally:
            b.close()


def to_pdf(snap, pdf_path, allow_local=None):
    """Render the snapshot to `pdf_path`. -> (ok: bool, pages: int). Never raises."""
    if os.environ.get("OWNER_MEET_PDF_DISABLED") == "1":
        return False, 0
    try:
        html, pages = render.print_html(snap, _font_base())
        html_tmp = pdf_path[:-4] + ".html" if pdf_path.endswith(".pdf") else pdf_path + ".html"
        with open(html_tmp, "w", encoding="utf-8") as f:
            f.write(html)
        try:
            from owner_report.renderer import ouja_render as r
            r._pw_pool.submit(_shared_print, html_tmp, pdf_path).result(timeout=PDF_TIMEOUT_S)
        except (ImportError, SyntaxError):
            if allow_local is False:
                return False, pages
            _local_print(html_tmp, pdf_path)
        ok = os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0
        return ok, pages
    except Exception:
        traceback.print_exc()
        try:
            from owner_report.renderer import ouja_render as r
            r._pw_state["browser"] = None
        except Exception:
            pass
        return False, 0
