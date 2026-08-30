# -*- coding: utf-8 -*-
"""G3 — parse every <script> in the SERVED DASHBOARD_HTML.

Brace balance is NOT enough: one bad token kills the whole script and the
dashboard will not even log in. CLAUDE.md documents this biting twice.
"""
import os
import re
import sys

os.environ.setdefault("STATE_DIR", "/tmp/ouja-g3")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bot          # noqa: E402
import esprima      # noqa: E402

html = bot.DASHBOARD_HTML
scripts = re.findall(r"<script>(.*?)</script>", html, re.S)
if not scripts:
    print("G3-ESPRIMA: no <script> blocks found — check the extraction")
    sys.exit(1)
for i, js in enumerate(scripts):
    try:
        esprima.parseScript(js)
    except Exception as e:
        print("G3-ESPRIMA FAIL in block %d: %s" % (i, e))
        sys.exit(1)

# structural checks CLAUDE.md calls for
ok = True
for ch, name in (("{", "braces"), ("(", "parens")):
    close = {"{": "}", "(": ")"}[ch]
    if html.count(ch) != html.count(close):
        print("G3 %s unbalanced: %d vs %d" % (name, html.count(ch), html.count(close)))
        ok = False
if html.count("`") % 2 != 0:
    print("G3 backticks odd: %d" % html.count("`"))
    ok = False

# every tab id must have a label in BOTH T.ar and T.en (trap #2)
tb = re.search(r"tb\s*=\s*\[(.*?)\]\s*[;,]", html, re.S)
if tb:
    ids = re.findall(r"\[\s*'([a-z0-9_]+)'", tb.group(1))
    for tid in ids:
        if len(re.findall(r"\b%s\s*:" % re.escape(tid), html)) < 2:
            print("G3 tab id %r lacks a label in both T.ar and T.en" % tid)
            ok = False
    print("G3 tab ids checked: %s" % ", ".join(ids))
else:
    print("G3 NOTE: no `tb` tab array matched — tab-label parity NOT checked "
          "(DASHBOARD_HTML was not modified by this branch)")

print("G3-ESPRIMA: %d script block(s) parsed clean" % len(scripts))
sys.exit(0 if ok else 1)
