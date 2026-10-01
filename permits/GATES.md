# Gates: Permit tracker «التصاريح»

OWNS: permits/**, tests/test_permits_*.py, tests/permits_fakes.py, tests/fixtures/permits/**, bot.py (PERMITS glue only), requirements.txt, CLAUDE.md, .gitignore, docs/superpowers/specs/2026-10-01-permits-tracker-design.md, docs/superpowers/plans/2026-10-01-permits-tracker.md

Scope: the permits/ package (seed, importer, engine, service, routes, dashboard tab JS), its Discord glue in bot.py (port, ticket view, loop, /permits), the tests, the spec + plan, and the CLAUDE.md section — shipped in DRY mode (no Discord output until an admin types «تشغيل»).

Run from the repo root: node <unlazy>/scripts/gate-check.mjs --cwd . permits/GATES.md

- [ ] G0: Baseline recorded before any change (test count + pre-existing failures)
  CHECK: test -f permits/.baseline.txt && grep -c "^Ran " permits/.baseline.txt
  EXPECT: /^1$/m
  EVIDENCE: pending

- [ ] G1: bot.py compiles clean with SyntaxWarning as error
  CHECK: rm -rf __pycache__ && python3 -W error::SyntaxWarning -m py_compile bot.py && echo OK_COMPILE
  EXPECT: OK_COMPILE
  EVIDENCE: pending

- [ ] G2: pyflakes clean on the new package (ignore "imported but unused")
  CHECK: test -f permits/routes.py && test -f permits/service.py && python3 -m pyflakes permits/ tests/test_permits_*.py tests/permits_fakes.py | grep -v "imported but unused" | wc -l | tr -d ' ' | sed 's/^0$/FLAKES_CLEAN/'
  EXPECT: /^FLAKES_CLEAN$/m
  EVIDENCE: pending

- [ ] G3: all permits tests pass, none skipped (Python 3.9 local, hijridate 2.5 dev-installed)
  CHECK: python3 -m unittest discover -s tests -p "test_permits_*.py" 2>&1 | python3 -c "import sys,re;t=sys.stdin.read();m=re.search(r'^Ran (\d+) tests',t,re.M);print('PERMITS_TESTS_OK ran=%s' % m.group(1) if m and int(m.group(1))>=100 and re.search(r'^OK$',t,re.M) else 'PERMITS_TESTS_BAD')"
  EXPECT: /^PERMITS_TESTS_OK ran=\d+$/m
  EVIDENCE: pending

- [ ] G3b: the pure permits tests also pass on Python 3.13 with hijridate 2.6 (Railway's runtime)
  CHECK: $PERMITS_PY313 -m unittest tests.test_permits_dates tests.test_permits_engine tests.test_permits_importer tests.test_permits_service tests.test_permits_seed_real 2>&1 | tail -3
  EXPECT: /^OK$/m
  EVIDENCE: pending

- [ ] G4: full suite — no NEW failures vs baseline
  CHECK: python3 permits/tools_compare_baseline.py
  EXPECT: /^NO_NEW_FAILURES/m
  EVIDENCE: pending

- [ ] G5: every DASHBOARD_HTML <script> parses (esprima) and the tab JS parses (node --check)
  CHECK: python3 -m unittest tests.test_permits_dashboard 2>&1 | tail -1
  EXPECT: /^OK$/m
  EVIDENCE: pending

- [ ] G6: no asyncio.to_thread in request handlers
  CHECK: test -f permits/routes.py && (grep -c "to_thread" permits/routes.py || true)
  EXPECT: /^0$/m
  EVIDENCE: pending

- [ ] G7: duplicate-proof — DB refuses a second live ticket (index present + race test)
  CHECK: python3 -m unittest tests.test_permits_service.RaceTest 2>&1 | tail -1
  EXPECT: /^OK$/m
  EVIDENCE: pending

- [ ] G8: nothing dropped — all 45 seed rows in the normalized JSON, F2 ends 2026-10-12, 6B ends 2027-08-04
  CHECK: python3 -c "import json;d=json.load(open('permits/seed/permits_seed.normalized.json'));r={x['permit_no']:x for x in d['rows']};print('SEED_OK' if d['source_rows']==45 and len(d['rows'])==45 and r['50035533']['end_date']=='2026-10-12' and r['50048967']['end_date']=='2027-08-04' else 'SEED_BAD')"
  EXPECT: /^SEED_OK$/m
  EVIDENCE: pending

- [ ] G9: default mode is dry on a fresh DB
  CHECK: python3 -m unittest tests.test_permits_service.DryDefaultTest 2>&1 | tail -1
  EXPECT: /^OK$/m
  EVIDENCE: pending

- [ ] G10: scope — only OWNS files differ from origin/main (committed or not)
  CHECK: { git diff --name-only origin/main; git ls-files -o --exclude-standard; } | sort -u | grep -vE '^(permits/|tests/test_permits_|tests/permits_fakes.py|tests/fixtures/permits/|bot.py$|requirements.txt$|CLAUDE.md$|\.gitignore$|docs/superpowers/(specs|plans)/2026-10-01-permits)' | wc -l | tr -d ' ' | sed 's/^0$/SCOPE_CLEAN/'
  EXPECT: /^SCOPE_CLEAN$/m
  EVIDENCE: pending

- [ ] G11: local smoke — real bot auth + role middleware in front of the package: tab JS served, summary answers with DASHBOARD_TOKEN, refuses without it
  CHECK: python3 permits/tools_smoke.py
  EXPECT: /^SMOKE_OK$/m
  EVIDENCE: pending

- [ ] G13: privacy — no national ID in any file that would be committed (added bot.py lines only), and the xlsx is git-ignored
  CHECK: python3 permits/tools_privacy_scan.py
  EXPECT: /^PRIVACY_OK$/m
  EVIDENCE: pending

- [ ] G14: real seed matches the oracle row-for-row
  CHECK: python3 -m unittest tests.test_permits_seed_real 2>&1 | tail -1
  EXPECT: /^OK$/m
  EVIDENCE: pending

- [ ] G15: Railway gets hijridate, and CLAUDE.md documents the package + fixes trap 2
  CHECK: grep -q "^hijridate~=2.6" requirements.txt && grep -q "the \`permits/\` package" CLAUDE.md && grep -q "NAV_DEF" CLAUDE.md && echo DOCS_OK
  EXPECT: /^DOCS_OK$/m
  EVIDENCE: pending

- [ ] G12: (manual, Faisal after deploy) dashboard tab shows all 45 seeded permits; banner says dry and lists F2 as the ticket that would open; typing «تشغيل» opens the due tickets under «صيانه»; next day 13:00 digest posts once.
  EVIDENCE: pending
