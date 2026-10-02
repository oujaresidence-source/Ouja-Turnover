# Gates: Review Push «رفع التقييم» (reviewask/)

OWNS: reviewask/**, tests/test_reviewask_*.py, bot.py, ops_tidy_rules.py, tests/test_ops_tidy_rules.py, CLAUDE.md, docs/superpowers/specs/2026-10-03-review-push-design.md, docs/superpowers/plans/2026-10-03-review-push.md

Scope: the owner-approved Review Push (spec 2026-10-03-review-push-design.md) — weak-apartment detection, one Discord room per qualifying checkout, WhatsApp + call ladder with text-only buttons, review-origin maintenance tickets, owner-edited templates, /تقييمات-بكرة, Checkout-Watch-style tracking, 7-day deletion of closed review rooms — shipped OFF, on a branch, not pushed.

- [ ] G0: baseline of the full suite captured on the untouched tree BEFORE the first edit
  CHECK: python3 -c "import re;t=open('.unlazy-baseline-rv.txt',encoding='utf-8').read();m=re.search(r'^Ran (\d+) tests',t,re.M);print('BASELINE_OK ran=%s'%m.group(1) if m else 'NO_BASELINE')"
  EXPECT: /^BASELINE_OK ran=\d+$/m
  EVIDENCE: pending

- [ ] G1: bot.py and every reviewask module compile clean (SyntaxWarning = error)
  CHECK: rm -rf __pycache__ reviewask/__pycache__ && python3 -W error::SyntaxWarning -m py_compile bot.py reviewask/*.py && echo COMPILED_OK
  EXPECT: /^COMPILED_OK$/m
  EVIDENCE: pending

- [ ] G2: no pyflakes findings in reviewask/ or its tests, none new in bot.py (unused imports allowed)
  CHECK: python3 -m pyflakes reviewask/*.py tests/test_reviewask_*.py bot.py | grep -v "imported but unused" | grep -c . | xargs -I{} sh -c 'test {} -eq 0 && echo FLAKES_OK || echo FLAKES_FOUND_{}'
  EXPECT: /^FLAKES_OK$/m
  EVIDENCE: pending

- [ ] G3: pure engine locks every owner rule — 4.75 in/out, <3 reviews, reviews_needed: (n=10,R=90)→11, (47,415)→64, (4,38)→1, call_time (20:00 / 20:45 May–Aug / 21:30 Ramadan / env override), max 2 calls, staff miss keeps the attempt, quiet 22:00–13:00, day-14 expiry, language by phone, unknown placeholder survives
  CHECK: python3 -m unittest tests.test_reviewask_engine 2>&1 | tail -1
  EXPECT: /^OK/m
  EVIDENCE: pending

- [ ] G4: flow + db — one room per reservation across 3 overlapping ticks, first-final-wins, a matched review closes from any open state, cancellation closes, /rv/<token> logs wa_opened and 302s to wa.me with the rendered template
  CHECK: python3 -m unittest tests.test_reviewask_flow 2>&1 | tail -1
  EXPECT: /^OK/m
  EVIDENCE: pending

- [ ] G5: deletion safety — only rv rooms closed ≥7 days whose topic carries the same reservation id are deleted; a wrong topic is refused; the transcript row exists before delete; "couldn't fetch" is never "deleted"
  CHECK: python3 -m unittest tests.test_reviewask_delete 2>&1 | tail -1
  EXPECT: /^OK/m
  EVIDENCE: pending

- [ ] G6: bot.py integration — «عنده ملاحظة» opens a maintenance room whose title starts «من مكالمة تقييم», source=review, field «المصدر», link back; existing _maint_open_ticket callers unchanged; commands registered; NAV labels in BOTH ar and en
  CHECK: python3 -m unittest tests.test_reviewask_bot 2>&1 | tail -1
  EXPECT: /^OK/m
  EVIDENCE: pending

- [ ] G7: structure — every button label in reviewask/ has no emoji, no `import bot`, no asyncio.to_thread, zero backslashes in reviewask/*.py, no discount text hard-coded in .py, channel.delete called only inside sweep_closed
  CHECK: python3 -m unittest tests.test_reviewask_structure 2>&1 | tail -1
  EXPECT: /^OK/m
  EVIDENCE: pending

- [ ] G8: ops_tidy never archives, locks or renames an ouja-rv: room, and its existing 2026-10-02 decisions are unchanged
  CHECK: python3 -m unittest tests.test_ops_tidy_rules 2>&1 | tail -1
  EXPECT: /^OK/m
  EVIDENCE: pending

- [ ] G9: full suite has no failure that is not already in the baseline
  CHECK: python3 -m unittest discover -s tests -p "test_*.py" 2>&1 | python3 -c "import sys,re;t=sys.stdin.read();b=open('.unlazy-baseline-rv.txt',encoding='utf-8').read();f=lambda s:set(re.findall(r'^(?:FAIL|ERROR): (\S+ \(\S+\))',s,re.M));new=f(t)-f(b);ran=re.search(r'^Ran (\d+) tests',t,re.M);print('NO_NEW_FAILURES ran=%s'%ran.group(1) if ran and not new else 'NEW_FAILURES %s'%sorted(new))"
  EXPECT: /^NO_NEW_FAILURES ran=\d+$/m
  EVIDENCE: pending

- [ ] G10: dashboard still logs in — every DASHBOARD_HTML <script> parses and the tab JS passes node --check
  CHECK: node --check reviewask/static/reviewask_tab.js && python3 -c "import bot,esprima,re;[esprima.parseScript(j) for j in re.findall(r'<script>(.*?)</script>',bot.DASHBOARD_HTML,re.S)];print('JS_OK')"
  EXPECT: /^JS_OK$/m
  EVIDENCE: pending

- [ ] G11: musaed selftest unaffected
  CHECK: python3 eval_musaed.py --selftest 2>&1 | tail -3
  EXPECT: /SELFTEST PASSED/i
  EVIDENCE: pending

- [ ] G12: live Hostaway review `type` / `channelName` values were printed and the guest-to-host + Airbnb filter in engine matches them (record the values here)
  EVIDENCE: pending

- [ ] G13: owner dry run — with REVIEWASK_LIVE=0, /تقييمات-بكرة replied with the would-open list and skip reasons for tomorrow; owner confirmed the list looks right before /تقييمات-تشغيل
  EVIDENCE: pending

- [ ] G14: on a real phone, «فتح واتساب» opened WhatsApp on the test number with the owner's saved message fully typed (Arabic and English), and the review link landed on Airbnb's reviews page
  EVIDENCE: pending

- [ ] G15: work sits on branch feat/review-push, committed, NOT on the remote — owner says when to push
  CHECK: test "$(git rev-parse --abbrev-ref HEAD)" = feat/review-push && test -z "$(git status --porcelain -- reviewask tests bot.py)" && test -z "$(git ls-remote --heads origin feat/review-push)" && echo BRANCH_LOCAL_OK
  EXPECT: /^BRANCH_LOCAL_OK$/m
  EVIDENCE: pending
