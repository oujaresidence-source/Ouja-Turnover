# Gates: Checkout Watch «متابعة الخروج»

OWNS: checkout/**, tests/test_checkout_watch_*.py, bot.py, CLAUDE.md, GATES.md

Scope: the checkout/ package (engine, db, texts, host, flow, board, risk, report, demo), its
Discord glue in bot.py (card, buttons, loop, six commands, demo), the oujact «no_answer» state,
the tests, and the CLAUDE.md section — shipped OFF until an admin runs /checkout-start.

- [x] G1: bot.py compiles clean
  CHECK: rm -rf __pycache__ && python3 -W error::SyntaxWarning -m py_compile bot.py && echo COMPILED_OK
  EXPECT: COMPILED_OK
  EVIDENCE: COMPILED_OK (python3 3.9.6, exit 0) — 2026-09-26

- [x] G2: checkout package + bot.py have no pyflakes errors (unused imports allowed)
  CHECK: python3 -m pyflakes checkout/*.py bot.py | grep -v "imported but unused" | grep -c . | xargs -I{} sh -c 'test {} -eq 0 && echo FLAKES_OK'
  EXPECT: FLAKES_OK
  EVIDENCE: FLAKES_OK — 0 non-unused-import findings across checkout/*.py + bot.py

- [x] G3: new tests pass
  CHECK: python3 -m unittest discover -s tests -p "test_checkout_watch*.py" 2>&1 | tail -1
  EXPECT: ^OK
  EVIDENCE: OK — Ran 92 tests (engine 34, flow 45, bot 13)

- [ ] G4: full suite still green
  CHECK: python3 -m unittest discover -s tests -p "test_*.py" 2>&1 | tail -1
  EXPECT: ^OK
  EVIDENCE: UNMET — last line is `sys:1: DeprecationWarning: builtin type swigvarlink…` (printed at interpreter exit, so `tail -1` can never be ^OK), and the suite has 2 failures that ALSO fail on untouched origin/main dcd11b5 (baseline run before any edit: Ran 4342, failures=2, the same two tests). See ABANDON below.

- [x] G4b: full suite has no failure beyond the two that already fail on untouched origin/main (dcd11b5)
  CHECK: python3 -m unittest discover -s tests -p "test_*.py" 2>&1 | python3 -c "import sys,re;t=sys.stdin.read();bad=set(re.findall(r'^(?:FAIL|ERROR): (\S+ \(\S+\))',t,re.M));ok={'test_an_unlinked_apartment_is_counted_as_unattributed (test_ops_capture.TestBackfill)','test_it_reports_how_much_it_could_attribute (test_ops_capture.TestBackfill)'};ran=re.search(r'^Ran (\d+) tests',t,re.M);print('NO_NEW_FAILURES ran=%s' % ran.group(1) if ran and bad<=ok else 'NEW_FAILURES %s' % sorted(bad-ok))"
  EXPECT: ^NO_NEW_FAILURES
  EVIDENCE: NO_NEW_FAILURES ran=4434 — the only failures are the two pre-existing test_ops_capture.TestBackfill ones (hard-coded 2026-07-29 dates now outside the 30-day window)

- [x] G5: musaed selftest unaffected
  CHECK: python3 eval_musaed.py --selftest 2>&1 | tail -3
  EXPECT: (?i)pass
  EVIDENCE: SELFTEST PASSED

- [x] G6: embedded dashboard JS still parses
  CHECK: python3 -c "import bot,esprima,re;[esprima.parseScript(j) for j in re.findall(r'<script>(.*?)</script>',bot.DASHBOARD_HTML,re.S)];print('JS_OK')"
  EXPECT: JS_OK
  EVIDENCE: JS_OK (DASHBOARD_HTML changed by one label entry: guest_out in the cleaning-log map)

- [x] G7: only allowed files changed
  CHECK: git status --porcelain | awk '{print $2}' | grep -v -E '^(bot\.py|CLAUDE\.md|GATES\.md|checkout/.*|tests/test_checkout_watch_.*\.py)$' | wc -l | xargs -I{} sh -c 'test {} -eq 0 && echo SCOPE_OK'
  EXPECT: SCOPE_OK
  EVIDENCE: SCOPE_OK — M CLAUDE.md, M bot.py, ?? GATES.md, ?? checkout/, ?? tests/test_checkout_watch_{bot,engine,flow}.py

- [ ] G8: MANUAL (owner, after deploy): /checkout-demo shows 5 channels; every button works; ⏩ advances; /checkout-demo-end removes them.
  EVIDENCE: pending

ABANDON: G4 cannot be met by this work: on untouched origin/main the full suite already has 2 failures (test_ops_capture.TestBackfill, date-expired fixtures) and the interpreter prints a DeprecationWarning after the verdict, so `tail -1` never shows OK. Fixing either means editing files outside this brief's allowed list. G4b proves no new failures. Handoff: owner decides whether to push.
