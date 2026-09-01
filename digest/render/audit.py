# -*- coding: utf-8 -*-
"""digest.render.audit — the layout checks that run on EVERY build (ported from
owner_report/renderer/audit_layout.py and extended). `.page{overflow:hidden}` means an
overflow leaves no trace in the PDF, so the page is measured in the live browser:
nothing may cross the footer, nothing may be wider than the page, every card has a
title that fits, every QR prints at >= 22 mm, no SVG text is clipped.

JS is passed as plain strings: ZERO backslashes in this file."""

QR_MIN_MM = 22

OVERFLOW_JS = """
() => {
  const out = [];
  const pages = document.querySelectorAll('.page, .story');
  pages.forEach((page, i) => {
    const pr = page.getBoundingClientRect();
    const foot = page.querySelector('.foot');
    const safeBottom = foot ? foot.getBoundingClientRect().top - 6 : pr.bottom - 40;
    page.querySelectorAll(':scope > *:not(.foot)').forEach(el => {
      const r = el.getBoundingClientRect();
      const over = Math.round(r.bottom - safeBottom);
      if (over > 2) out.push('page ' + (i + 1) + ': OVERFLOW ' + over + 'px past the footer: ' + el.className);
      if (r.right > pr.right + 1 || r.left < pr.left - 1) out.push('page ' + (i + 1) + ': WIDER than the page: ' + el.className);
    });
    page.querySelectorAll('.card').forEach((c, j) => {
      const t = c.querySelector('.ttl');
      if (!t || !t.textContent.trim()) out.push('page ' + (i + 1) + ': card ' + (j + 1) + ' has no title');
      const cr = c.getBoundingClientRect();
      c.querySelectorAll('.ttl, .sub, .row').forEach(el => {
        const r = el.getBoundingClientRect();
        if (r.bottom > cr.bottom + 1) out.push('page ' + (i + 1) + ': card ' + (j + 1) + ' content overflows the card: ' + el.className);
        if (r.right > cr.right + 1 || r.left < cr.left - 1) out.push('page ' + (i + 1) + ': card ' + (j + 1) + ' content wider than the card: ' + el.className);
      });
    });
    page.querySelectorAll('.qr').forEach((q, j) => {
      const r = q.getBoundingClientRect();
      const mm = r.width / 96 * 25.4;
      if (page.classList.contains('page') && mm < %(qr)d - 0.5) out.push('page ' + (i + 1) + ': QR ' + (j + 1) + ' prints at ' + mm.toFixed(1) + 'mm (< %(qr)dmm)');
    });
  });
  document.querySelectorAll('svg text').forEach((t, i) => {
    const r = t.getBoundingClientRect();
    const sb = t.ownerSVGElement.getBoundingClientRect();
    if (r.right - sb.right > 1 || sb.left - r.left > 1 || r.bottom - sb.bottom > 1 || sb.top - r.top > 1) {
      out.push('svg text ' + (i + 1) + ' clipped: ' + t.textContent.slice(0, 30));
    }
  });
  return out;
}
""" % {"qr": QR_MIN_MM}

LAYOUT_JS = """
() => Array.from(document.querySelectorAll('.page, .page > *, .card, .claim, .ttl, .qr, .art, .band, table.fix')).map(el => {
  const r = el.getBoundingClientRect();
  return [el.tagName.toLowerCase() + '.' + (el.className || ''), Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height)];
})
"""


def audit_page(page):
    """`page` is an open Playwright page with the document loaded. -> [violations]."""
    return list(page.evaluate(OVERFLOW_JS) or [])


def layout_of(page):
    return page.evaluate(LAYOUT_JS) or []


class LayoutError(RuntimeError):
    """The page is broken — it must not reach the owner."""


def assert_clean(violations, label=""):
    if violations:
        raise LayoutError("layout audit failed%s:%s  %s" % ((" for " + label) if label else "", chr(10), (chr(10) + "  ").join(violations)))
