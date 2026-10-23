# -*- coding: utf-8 -*-
"""Gate G4: the served DASHBOARD_HTML must parse, and every NAV tab must have both labels.

Reads bot.py as TEXT for the NAV block and imports nothing from bot (importing it boots a
Discord bot). The HTML string is evaluated by compiling ONLY its assignment, so the Python
string escapes are applied exactly as the running bot applies them — that is the whole trap.
    python3 -m rrdesk.tools_dash_check   ->  DASH_OK scripts=<n> tabs=<n>
"""
import ast
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _dashboard_html(src):
    tree = ast.parse(src)
    parts = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "DASHBOARD_HTML"
                                                for t in node.targets):
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                parts.append(node.value.value)
    if not parts:
        raise SystemExit("NO_DASHBOARD_HTML")
    return parts[0]


def _nav(src):
    i = src.index("NAV_DEF = {")
    j = src.index(NL_END, i)
    return ast.literal_eval(src[i + len("NAV_DEF = "):j + 2])


NL_END = chr(10) + "}" + chr(10)


def main():
    import esprima
    with open(os.path.join(ROOT, "bot.py"), encoding="utf-8") as f:
        src = f.read()
    html = _dashboard_html(src)
    scripts = re.findall(r"<script>(.*?)</script>", html, re.S)
    for js in scripts:
        esprima.parseScript(js)
    nav = _nav(src)
    ids = [it["id"] for it in nav["items"]]
    labels = nav.get("labels") or {}
    missing = [i for i in ids if i not in (labels.get("ar") or {}) or i not in (labels.get("en") or {})]
    if missing:
        print("NAV_LABELS_MISSING " + ",".join(missing))
        return 1
    print("DASH_OK scripts=%d tabs=%d" % (len(scripts), len(ids)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
