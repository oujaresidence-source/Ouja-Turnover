# Gates: Discord tidy «ترتيب ديسكورد» (`!ouja-tidy`)

OWNS: ops_tidy.py, ops_tidy_rules.py, tests/test_ops_tidy*.py, tests/fixtures/tidy/**, bot.py, CLAUDE.md, GATES.md

Scope: the `!ouja-tidy plan|run|undo|status` command (ops_tidy.py, executing the pure plan from
ops_tidy_rules.py), plus five targeted bot.py edits: env-gated members intent, overflow categories
copy their parent's overwrites, the directpay category is created locked, closed tickets auto-move
to «📦 أرشيف N», and archived directpay rooms are still "known" (and move back on reopen).
Spec: docs/superpowers/specs/2026-10-02-discord-tidy-design.md

- [x] G0: baseline captured BEFORE any edit (full suite on the untouched tree)
  CHECK: test -f .unlazy-baseline.txt && grep -c "^Ran " .unlazy-baseline.txt | xargs -I{} sh -c 'test {} -ge 1 && echo BASELINE_OK'
  EXPECT: BASELINE_OK
  EVIDENCE (2026-10-02): BASELINE_OK (4683 tests; 2 pre-existing failures: test_ops_capture.TestBackfill ×2, expired dates)

- [x] G1: bot.py and the new modules compile clean
  CHECK: rm -rf __pycache__ && python3 -W error::SyntaxWarning -m py_compile bot.py ops_tidy.py ops_tidy_rules.py && echo COMPILED_OK
  EXPECT: COMPILED_OK
  EVIDENCE (2026-10-02): COMPILED_OK

- [x] G2: no pyflakes findings in the new modules/tests and none new in bot.py (unused imports allowed)
  CHECK: python3 -m pyflakes ops_tidy.py ops_tidy_rules.py tests/test_ops_tidy*.py bot.py | grep -v "imported but unused" | grep -c . | xargs -I{} sh -c 'test {} -eq 0 && echo FLAKES_OK'
  EXPECT: FLAKES_OK
  EVIDENCE (2026-10-02): FLAKES_OK

- [x] G3: the owner-approved decisions still hold (pure rules, real 2026-10-02 audit)
  CHECK: python3 -m unittest tests.test_ops_tidy_rules 2>&1 | grep -E "^(OK|FAILED)"
  EXPECT: ^OK$
  EVIDENCE (2026-10-02): OK (23 tests)

- [x] G4: the Discord layer + bot.py integration tests pass (fakes, no network)
  CHECK: python3 -m unittest discover -s tests -p "test_ops_tidy_*.py" 2>&1 | grep -E "^(OK|FAILED)"
  EXPECT: ^OK$
  EVIDENCE (2026-10-02): OK (50 tests)

- [x] G5: full suite has no failure that is not already in the baseline
  CHECK: python3 -m unittest discover -s tests -p "test_*.py" 2>&1 | python3 -c "import sys,re;t=sys.stdin.read();b=open('.unlazy-baseline.txt').read();f=lambda s:set(re.findall(r'^(?:FAIL|ERROR): (\S+ \(\S+\))',s,re.M));new=f(t)-f(b);ran=re.search(r'^Ran (\d+) tests',t,re.M);print('NO_NEW_FAILURES ran=%s'%ran.group(1) if ran and not new else 'NEW_FAILURES %s'%sorted(new))"
  EXPECT: ^NO_NEW_FAILURES
  EVIDENCE (2026-10-02): NO_NEW_FAILURES ran=4733

- [x] G6: embedded dashboard JS still parses
  CHECK: python3 -c "import bot,esprima,re;[esprima.parseScript(j) for j in re.findall(r'<script>(.*?)</script>',bot.DASHBOARD_HTML,re.S)];print('JS_OK')"
  EXPECT: JS_OK
  EVIDENCE (2026-10-02): JS_OK

- [x] G7: musaed selftest unaffected
  CHECK: python3 eval_musaed.py --selftest 2>&1 | tail -3
  EXPECT: (?i)pass
  EVIDENCE (2026-10-02): SELFTEST PASSED

- [x] G8: members intent is env-gated (bot must still boot when the portal toggle is OFF)
  CHECK: python3 -c "import re;s=open('bot.py',encoding='utf-8').read();m=re.findall(r'^intents\.members\s*=.*$',s,re.M);print('GATED_OK' if len(m)==1 and 'MEMBERS_INTENT' in m[0] else 'BAD %r'%m)"
  EXPECT: ^GATED_OK$
  EVIDENCE (2026-10-02): GATED_OK

- [x] G9: ops_tidy is wired exactly like ops_audit/ops_archive and never imports bot
  CHECK: python3 -c "import re;s=open('bot.py',encoding='utf-8').read();t=open('ops_tidy.py',encoding='utf-8').read();ok=('ops_tidy.setup(bot' in s) and not re.search(r'^\s*(import bot\b|from bot import)',t,re.M) and bool(re.search(r'^\s*(import ops_tidy_rules|from ops_tidy_rules import)',t,re.M));print('WIRED_OK' if ok else 'NOT_WIRED')"
  EXPECT: ^WIRED_OK$
  EVIDENCE (2026-10-02): WIRED_OK

- [x] G10: plan is read-only (fake guild records ZERO edits/creates/deletes during `plan`)
  CHECK: python3 -m unittest tests.test_ops_tidy_discord.TestPlanIsReadOnly 2>&1 | grep -E "^(OK|FAILED)"
  EXPECT: ^OK$
  EVIDENCE (2026-10-02): OK

- [x] G11: ticket-opening rooms are never edited by run, undo, or auto-archive
  CHECK: python3 -m unittest tests.test_ops_tidy_discord.TestPanelsUntouched 2>&1 | grep -E "^(OK|FAILED)"
  EXPECT: ^OK$
  EVIDENCE (2026-10-02): OK

- [x] G12: nothing is ever deleted or renamed by ops_tidy.py
  CHECK: python3 -c "import re;t=open('ops_tidy.py',encoding='utf-8').read();bad=re.findall(r'\.delete\(|\.edit\([^)]*\bname\s*=',t);print('NO_DELETE_OK' if not bad else 'FOUND %r'%bad)"
  EXPECT: ^NO_DELETE_OK$
  EVIDENCE (2026-10-02): NO_DELETE_OK

## Result — 13/13 MET (2026-10-02)
Independent review before shipping found 4 real issues, all fixed test-first and re-gated:
the bot must not grant itself Manage Permissions in an overwrite (admin-only → 403 after the run);
moves pass the archive overwrites explicitly (gateway-cache lag); an unconfirmed category lock
never syncs its channels; undo writes a position only when it changed; a reopened collection room
returns to the first collection category with room.
