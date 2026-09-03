# -*- coding: utf-8 -*-
"""digest.render.build — HTML -> PDF (810×1440 pt) + story PNG (1080×1920) + JSON.

Pipeline borrowed from cp/tools/build_pdf.py and owner_report/renderer/ouja_render.py:
write the HTML to disk, open it as file:// in a headless Chromium, wait for the fonts,
run the layout audit, print. The sync Playwright API is greenlet-bound, so all browser
work is pinned to a one-worker pool (the owner_report lesson). Chromium is launched per
build and closed in `finally` — one digest a week does not justify a resident browser.

No network: fonts are file://, artwork is inline SVG or data URIs, links are plain <a href>."""

import hashlib
import json
import os
import pathlib
from concurrent.futures import ThreadPoolExecutor

from . import audit, html as html_mod, poster as poster_mod, tokens

_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ouja-digest-pdf")


class RenderError(RuntimeError):
    pass


def _md5(b):
    return hashlib.md5(b).hexdigest()


def chromium_available():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False
    try:
        def _probe():
            with sync_playwright() as pw:
                b = pw.chromium.launch(args=["--disable-dev-shm-usage"])
                v = b.version
                b.close()
                return v
        return bool(_pool.submit(_probe).result(timeout=60))
    except Exception:
        return False


def _render_in_browser(pages_html_path, story_html_path, pdf_path, png_path, run_audit, poster_html_path=None, poster_png_path=None):
    from playwright.sync_api import sync_playwright
    result = {"audit": [], "layout": [], "chromium": ""}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--disable-dev-shm-usage"])
        result["chromium"] = browser.version
        try:
            ctx = browser.new_context(viewport={"width": 1080, "height": 1440}, device_scale_factor=1)
            pg = ctx.new_page()
            pg.goto("file://" + str(pathlib.Path(pages_html_path).resolve()), wait_until="load")
            pg.evaluate("() => document.fonts.ready")
            pg.wait_for_timeout(400)
            result["audit"] = audit.audit_page(pg)
            if run_audit:
                audit.assert_clean(result["audit"], "digest pages")
            result["layout"] = audit.layout_of(pg)
            # Playwright's pdf() takes px/in/cm/mm, not pt: 810×1440 pt = 11.25×20 in.
            pg.pdf(path=str(pdf_path), width="%.4fin" % (tokens.PAGE_W_PT / 72.0), height="%.4fin" % (tokens.PAGE_H_PT / 72.0),
                   print_background=True, prefer_css_page_size=True,
                   margin={"top": "0", "bottom": "0", "left": "0", "right": "0"})
            pg.close()
            ctx.close()
            sctx = browser.new_context(viewport={"width": tokens.STORY_CSS_W, "height": tokens.STORY_CSS_H},
                                       device_scale_factor=2)
            sp = sctx.new_page()
            sp.goto("file://" + str(pathlib.Path(story_html_path).resolve()), wait_until="load")
            sp.evaluate("() => document.fonts.ready")
            sp.wait_for_timeout(300)
            story_audit = audit.audit_page(sp)
            result["audit"] += ["story: " + v for v in story_audit]
            if run_audit:
                audit.assert_clean(story_audit, "digest story")
            sp.screenshot(path=str(png_path), type="png", full_page=False)
            sp.close()
            sctx.close()
            if poster_html_path and poster_png_path:
                pctx = browser.new_context(viewport={"width": tokens.STORY_CSS_W, "height": 900}, device_scale_factor=2)
                pp = pctx.new_page()
                pp.goto("file://" + str(pathlib.Path(poster_html_path).resolve()), wait_until="load")
                pp.evaluate("() => document.fonts.ready")
                pp.wait_for_timeout(300)
                result["poster_height"] = pp.evaluate("() => document.querySelector('.poster').getBoundingClientRect().height")
                pp.screenshot(path=str(poster_png_path), type="png", full_page=True)
                pp.close()
                pctx.close()
        finally:
            browser.close()
    return result


def render(payload, art_map, out_dir, issue_no, run_audit=True, guard_ctx=None):
    """-> {"pdf","png","json","html","story_html","audit","layout_md5","chromium"}.
    `guard_ctx` = (week, now) runs digest.guard.assert_clean on the HTML first."""
    out = pathlib.Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    pages_html = html_mod.build_pages(payload, art_map)
    story_html = html_mod.build_story(payload, art_map)
    poster_html = poster_mod.build_poster(payload, art_map)
    if guard_ctx:
        from .. import guard
        week, now = guard_ctx
        guard.assert_clean(pages_html, payload, week, now)
        guard.assert_clean(story_html, payload, week, now)
    stem = "digest-%s" % issue_no
    paths = {
        "html": out / ("%s.html" % stem),
        "story_html": out / ("%s.story.html" % stem),
        "poster_html": out / ("%s.poster.html" % stem),
        "poster": out / ("%s.poster.png" % stem),
        "pdf": out / ("%s.pdf" % stem),
        "png": out / ("%s.png" % stem),
        "json": out / ("%s.json" % stem),
    }
    paths["html"].write_text(pages_html, encoding="utf-8")
    paths["story_html"].write_text(story_html, encoding="utf-8")
    paths["poster_html"].write_text(poster_html, encoding="utf-8")
    paths["json"].write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        res = _pool.submit(_render_in_browser, paths["html"], paths["story_html"], paths["pdf"], paths["png"], run_audit,
                           paths["poster_html"], paths["poster"]).result()
    except audit.LayoutError:
        raise
    except Exception as e:
        raise RenderError("chromium render failed: %s: %s" % (type(e).__name__, e))
    layout_json = json.dumps(res["layout"], ensure_ascii=False, separators=(",", ":"))
    (out / ("%s.layout.json" % stem)).write_text(layout_json, encoding="utf-8")
    return {
        "pdf": str(paths["pdf"]), "png": str(paths["png"]), "json": str(paths["json"]),
        "html": str(paths["html"]), "story_html": str(paths["story_html"]),
        "poster": str(paths["poster"]), "poster_html": str(paths["poster_html"]), "poster_height": res.get("poster_height"),
        "audit": res["audit"], "layout_md5": _md5(layout_json.encode("utf-8")),
        "layout": res["layout"], "chromium": res["chromium"],
        "html_sha": hashlib.sha256(pages_html.encode("utf-8")).hexdigest(),
    }


def reference_payload():
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "reference_payload.json"), encoding="utf-8") as fh:
        return json.load(fh)
