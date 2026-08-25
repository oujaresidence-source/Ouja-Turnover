# -*- coding: utf-8 -*-
"""
LAYOUT AUDIT — run on EVERY generated report, not just the reference one.

The golden test proves the renderer is untouched. This proves that *real data*
doesn't break the layout — a long unit name, a 6-competitor comp set, or a big
number can still push content off the page.

Two checks:
  1. OVERFLOW    — no element may extend past the footer on any page.
  2. CHART CLIP  — no SVG <text> may escape its chart's bounding box.

Both must return zero violations before a PDF is released to an owner.

    from audit_layout import audit_html
    violations = audit_html(html_string)   # [] == clean
"""
import pathlib
import tempfile

from playwright.sync_api import sync_playwright

_OVERFLOW_JS = """() => {
  const out = [];
  document.querySelectorAll('.page').forEach((page, i) => {
    if (page.classList.contains('cover')) return;           // cover footer is full-bleed by design
    const foot = page.querySelector('.rf');
    const pr = page.getBoundingClientRect();
    const safeBottom = foot ? foot.getBoundingClientRect().top - 6 : pr.bottom - 49;
    page.querySelectorAll(':scope > *:not(.rf)').forEach(el => {
      const r = el.getBoundingClientRect();
      const over = Math.round(r.bottom - safeBottom);
      if (over > 2) out.push(`page ${i + 1}: OVERFLOW ${over}px — <${el.tagName.toLowerCase()} class="${el.className}">`);
    });
  });
  return out;
}"""

_CLIP_JS = """() => {
  const out = [];
  document.querySelectorAll('svg.chart').forEach((svg, i) => {
    const sb = svg.getBoundingClientRect();
    svg.querySelectorAll('text').forEach(t => {
      const r = t.getBoundingClientRect();
      if (r.right - sb.right > 1 || sb.left - r.left > 1 || r.bottom - sb.bottom > 1)
        out.push(`chart ${i + 1}: CLIPPED LABEL — "${t.textContent.slice(0, 40)}"`);
    });
  });
  return out;
}"""


def audit_html(html: str) -> list[str]:
    """Return a list of layout violations. Empty list == clean."""
    with tempfile.TemporaryDirectory() as tmp:
        f = pathlib.Path(tmp) / "audit.html"
        f.write_text(html, encoding="utf-8")
        with sync_playwright() as p:
            b = p.chromium.launch()
            pg = b.new_page()
            pg.goto("file://" + str(f.resolve()))
            pg.wait_for_timeout(1400)
            violations = pg.evaluate(_OVERFLOW_JS) + pg.evaluate(_CLIP_JS)
            b.close()
    return violations


def assert_clean(html: str) -> None:
    """Raise if the layout is broken. Call this before releasing any PDF."""
    v = audit_html(html)
    if v:
        raise RuntimeError(
            "Layout audit failed — this report must not be sent to an owner:\n  "
            + "\n  ".join(v)
        )
