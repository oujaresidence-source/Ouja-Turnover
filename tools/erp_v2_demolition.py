# -*- coding: utf-8 -*-
"""ERP v2 Slice 8 — one-shot surgical demolition of the three condemned
dashboard views (fb / expenses / finance) inside bot.py.

Every cut is anchored: the script ABORTS (no write) unless each boundary line
contains the exact expected text. Deletions are applied bottom-up so earlier
line numbers stay valid. Run once; idempotence guard: refuses if the fb view
section is already gone.
"""
import io
import sys

PATH = "bot.py"
src = io.open(PATH, encoding="utf-8").read().split("\n")


def L(i):
    return src[i - 1]


def need(i, sub):
    if sub not in L(i):
        sys.exit("ABORT: line %d does not contain %r — got: %r" % (i, sub, L(i)[:120]))


if 'id="view_fb"' not in "\n".join(src):
    sys.exit("ABORT: view_fb already gone — demolition already ran?")

# ---------- anchors (verified against HEAD) ----------
need(12772, '<section class="view" id="view_fb">')
need(12785, "</section>")
need(13205, '<section class="view" id="view_finance">')
need(13367, '<section class="view" id="view_expenses">')
need(15287, "case 'expenses': return expRefresh();")
need(15307, "case 'finance':  return loadFinance();")
need(15313, "case 'fb':       return loadFb();")
need(15331, "if(id==='fb') loadFb();")
need(15351, "if(id==='expenses') loadExpenses();")
need(15352, "if(id==='finance') loadFinance();")
need(18508, "async function expShowSettings(){")
need(18893, "DESIGN REQUESTS")
need(22055, "async function loadFinance(){")
need(22451, "Pricing Lab")
need(22706, "Financial Brain")
need(23736, "Guest Website")
need(24101, "Bulk owner-statement PDFs")
need(24358, "async function loadLearnings(){")


def section_end(start):
    """First '      </section>' at/after start."""
    i = start
    while i <= len(src):
        if L(i).strip() == "</section>":
            return i
        i += 1
    sys.exit("ABORT: no </section> after %d" % start)


fin_html_end = section_end(13205)
exp_html_end = section_end(13367)
need(fin_html_end + 0, "</section>")
need(exp_html_end + 0, "</section>")

# shared style helpers used by the GW view — preserved verbatim from the fb block
KEEP = [
    "/* ===== shared style helpers (were part of the deleted fb view; GW uses them) ===== */",
    L(22709),   # fbCard
    L(22710),   # fbChip
    L(23073),   # fbInp
]
need(22709, "function fbCard()")
need(22710, "function fbChip(")
need(23073, "function fbInp()")
# fbStatCard is multi-line? verify single line
need(23582, "function fbStatCard(")
stat_line = L(23582)
if stat_line.count("{") != stat_line.count("}"):
    sys.exit("ABORT: fbStatCard is not single-line — handle manually")
KEEP.append(stat_line)

# ---------- patches on single lines (before deletions, bottom-up overall) ----------
# global-search: expenses jump goes straight through go() (which now redirects);
# the old setTimeout called the deleted x4Detail.
gs = None
for i in range(24760, 24800):
    if "x4Detail(" in L(i):
        gs = i
        break
if not gs:
    sys.exit("ABORT: gsIndex x4Detail jump not found")
src[gs - 1] = src[gs - 1].split("jump:function()")[0] + "jump:function(){ gsClose(); go('expenses'); }});"

# renderAllPageOps: drop the two deleted strips
need(14874, "renderExpensesOpsSummary(); renderFinanceOpsSummary();")
src[14874 - 1] = src[14874 - 1].replace(" renderExpensesOpsSummary(); renderFinanceOpsSummary();", "")

# locate + delete the two ops-summary function bodies (small, contiguous)
def func_block(name, lo, hi):
    s = None
    for i in range(lo, hi):
        if L(i).startswith("function " + name + "(") or L(i).startswith("async function " + name + "("):
            s = i
            break
    if not s:
        sys.exit("ABORT: %s not found" % name)
    i = s + 1
    while i <= hi and not (L(i).startswith("function ") or L(i).startswith("async function ")):
        i += 1
    return s, i - 1


exp_ops_s, exp_ops_e = func_block("renderExpensesOpsSummary", 14700, 14900)
fin_ops_s, fin_ops_e = func_block("renderFinanceOpsSummary", 14700, 14900)

# go()/refreshView dispatch + erp redirect upgrade
need_line = None
for i in range(15300, 15330):
    if "if(id==='erp')" in L(i):
        need_line = i
        break
if not need_line:
    sys.exit("ABORT: erp redirect line not found in go()")
src[need_line - 1] = ("  if(id==='erp'||id==='fb'||id==='finance'||id==='expenses'){ "
                      "var _ws={erp:'today',fb:'today',finance:'owners',expenses:'exp'}[id]; "
                      "window.location.href='/erp?token='+encodeURIComponent(tok())+'#'+_ws; return; }   "
                      "// old finance views are cut over to ERP v2")

# ---------- ranged deletions (bottom-up) ----------
cuts = [
    (24101, 24357),            # bulk PDFs + client-side statement PDF/ZIP engine
    (22706, 23735),            # fb view JS (helpers re-inserted below)
    (22055, 22450),            # finance view JS (loadFinance … finLineClear)
    (18508, 18891),            # expenses V4 view JS (settings + loadExpenses … x4FilesHtml)
    (15351, 15352),            # go() late-load triggers (expenses/finance)
    (15331, 15331),            # go() late-load trigger (fb)
    (15313, 15313),            # refreshView case fb
    (15307, 15307),            # refreshView case finance
    (15287, 15287),            # refreshView case expenses
    (fin_ops_s, fin_ops_e),    # renderFinanceOpsSummary
    (exp_ops_s, exp_ops_e),    # renderExpensesOpsSummary
    (13367, exp_html_end),     # view_expenses HTML
    (13205, fin_html_end),     # view_finance HTML
    (12772, 12785),            # view_fb HTML
]
# sanity: no overlapping ranges
flat = sorted(cuts)
for a, b in zip(flat, flat[1:]):
    if a[1] >= b[0]:
        sys.exit("ABORT: overlapping cut ranges %s %s" % (a, b))

for s, e in sorted(cuts, reverse=True):
    del src[s - 1:e]

# re-insert the kept GW helpers right before the Guest Website block
gw_at = None
for i, line in enumerate(src):
    if "Guest Website" in line and "=====" in line:
        gw_at = i
        break
if gw_at is None:
    sys.exit("ABORT: Guest Website marker lost")
src[gw_at:gw_at] = KEEP

io.open(PATH, "w", encoding="utf-8").write("\n".join(src))
print("DEMOLITION APPLIED: %d ranged cuts; kept %d shared helper lines; new length %d lines"
      % (len(cuts), len(KEEP) - 1, len(src)))
