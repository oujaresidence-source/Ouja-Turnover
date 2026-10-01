# Gates: Permit tracker «التصاريح»

OWNS: permits/**, tests/test_permits_*.py, tests/permits_fakes.py, tests/fixtures/permits/**, bot.py (PERMITS glue only), requirements.txt, CLAUDE.md, .gitignore, docs/superpowers/specs/2026-10-01-permits-tracker-design.md, docs/superpowers/plans/2026-10-01-permits-tracker.md

Scope: the permits/ package (seed, importer, engine, service, routes, dashboard tab JS), its Discord glue in bot.py (port, ticket view, loop, /permits), the tests, the spec + plan, and the CLAUDE.md section — shipped in DRY mode (no Discord output until an admin types «تشغيل»).

Run from the repo root: node <unlazy>/scripts/gate-check.mjs --cwd . permits/GATES.md

- [x] G0: Baseline recorded before any change (test count + pre-existing failures)
  CHECK: test -f permits/.baseline.txt && grep -c "^Ran " permits/.baseline.txt
  EXPECT: /^1$/m
  EVIDENCE: automatic-evidence=v1; definition-sha256=1b88d605a6d6fc72bccda8749ec7c12a368c6f4ce752234cfc64041d73acadaa; exit=0; EXPECT=matched; output-sha256=4355a46b19d348dc2f57c046f8ef63d4538ebb936000f3c9ee954a27460dd865; output-bytes=2; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-permits; path=82de56a067b7/18 entries

- [x] G1: bot.py compiles clean with SyntaxWarning as error
  CHECK: rm -rf __pycache__ && python3 -W error::SyntaxWarning -m py_compile bot.py && echo OK_COMPILE
  EXPECT: OK_COMPILE
  EVIDENCE: automatic-evidence=v1; definition-sha256=3487d7525b38899cd6fd012ea990ff619fdd87d7cc6f46812799ae1379b3a43a; exit=0; EXPECT=matched; output-sha256=54c4da2cec9fcd400f2f5ba44a954cdb7622e944e0642dfed41213c608092359; output-bytes=11; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-permits; path=82de56a067b7/18 entries

- [x] G2: pyflakes clean on the new package (ignore "imported but unused")
  CHECK: test -f permits/routes.py && test -f permits/service.py && python3 -m pyflakes permits/ tests/test_permits_*.py tests/permits_fakes.py | grep -v "imported but unused" | wc -l | tr -d ' ' | sed 's/^0$/FLAKES_CLEAN/'
  EXPECT: /^FLAKES_CLEAN$/m
  EVIDENCE: automatic-evidence=v1; definition-sha256=0cfecd163755995b551d8a53e627cfa27b9fad6fb22ea780f9cafed8c3c76ab4; exit=0; EXPECT=matched; output-sha256=948963639f94dc5c4dfa63210ebf942cecf1ff8fc8308c49be432c6ac1029b71; output-bytes=13; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-permits; path=82de56a067b7/18 entries

- [x] G3: all permits tests pass, none skipped (Python 3.9 local, hijridate 2.5 dev-installed)
  CHECK: python3 -m unittest discover -s tests -p "test_permits_*.py" 2>&1 | python3 -c "import sys,re;t=sys.stdin.read();m=re.search(r'^Ran (\d+) tests',t,re.M);print('PERMITS_TESTS_OK ran=%s' % m.group(1) if m and int(m.group(1))>=100 and re.search(r'^OK$',t,re.M) else 'PERMITS_TESTS_BAD')"
  EXPECT: /^PERMITS_TESTS_OK ran=\d+$/m
  EVIDENCE: automatic-evidence=v1; definition-sha256=68133c339c64fe037d2646f70456fcbca7db14def9a2ef5801704c3f7c11d088; exit=0; EXPECT=matched; output-sha256=62b0f635047bd39283e3eefb600bb620fc4b757d36eeb721423ca473d23ddc9b; output-bytes=25; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-permits; path=82de56a067b7/18 entries

- [x] G3b: the pure permits tests also pass on Python 3.13 with hijridate 2.6 (Railway's runtime)
  CHECK: $PERMITS_PY313 -m unittest tests.test_permits_dates tests.test_permits_engine tests.test_permits_importer tests.test_permits_service tests.test_permits_seed_real 2>&1 | grep -E '^(Ran [0-9]+ tests|OK|FAILED)'
  EXPECT: /^OK$/m
  EVIDENCE: automatic-evidence=v1; definition-sha256=400a6b4b92c46ff64dbe287cad87f5c2608141659efad9cadb801104252df6d0; exit=0; EXPECT=matched; output-sha256=d6ab60c601c72294062bc0d9867aff731ec39df67c5ed8e090ce0ba6d0c9db6d; output-bytes=27; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-permits; path=82de56a067b7/18 entries

- [x] G4: full suite — no NEW failures vs baseline
  CHECK: python3 permits/tools_compare_baseline.py
  EXPECT: /^NO_NEW_FAILURES/m
  EVIDENCE: automatic-evidence=v1; definition-sha256=2d2acac2610e5ceb3412c058a6f5d0a4e5769842c87a76afb2643edbc2dfc1c8; exit=0; EXPECT=matched; output-sha256=269ef91c3ce726413fa74d56b0ef25deaf0c20f7ae2b8dd454107ecbcc1af268; output-bytes=43; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-permits; path=82de56a067b7/18 entries

- [x] G5: every DASHBOARD_HTML <script> parses (esprima) and the tab JS parses (node --check)
  CHECK: python3 -m unittest tests.test_permits_dashboard 2>&1 | grep -E '^(Ran [0-9]+ tests|OK|FAILED)'
  EXPECT: /^OK$/m
  EVIDENCE: automatic-evidence=v1; definition-sha256=bffedcf07ef10fd5c549488a1e6c558bfcad3edef7a79ff1e8087d8ced144fca; exit=0; EXPECT=matched; output-sha256=08dac8a6ab0a8127790ebb3e0f45de2caacdd0572fed3afd3c539eb7534891be; output-bytes=26; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-permits; path=82de56a067b7/18 entries

- [x] G6: no asyncio.to_thread in request handlers
  CHECK: test -f permits/routes.py && (grep -c "to_thread" permits/routes.py || true)
  EXPECT: /^0$/m
  EVIDENCE: automatic-evidence=v1; definition-sha256=2021253a982abf9b6088470dd54d5e972ec0a881344d6e483e157f81b829d285; exit=0; EXPECT=matched; output-sha256=9a271f2a916b0b6ee6cecb2426f0b3206ef074578be55d9bc94f6f3fe3ab86aa; output-bytes=2; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-permits; path=82de56a067b7/18 entries

- [x] G7: duplicate-proof — DB refuses a second live ticket (index present + race test)
  CHECK: python3 -m unittest tests.test_permits_service.RaceTest 2>&1 | grep -E '^(Ran [0-9]+ tests|OK|FAILED)'
  EXPECT: /^OK$/m
  EVIDENCE: automatic-evidence=v1; definition-sha256=252f57b1482e010ec123d977d80576a0e30c3127fe6b8a4c3f0515f0f4852739; exit=0; EXPECT=matched; output-sha256=9997c356ed8b5b2e7b57cf6768dff2029aef6425377a3c2156a282ab154b7746; output-bytes=25; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-permits; path=82de56a067b7/18 entries

- [x] G8: nothing dropped — all 45 seed rows in the normalized JSON, F2 ends 2026-10-12, 6B ends 2027-08-04
  CHECK: python3 -c "import json;d=json.load(open('permits/seed/permits_seed.normalized.json'));r={x['permit_no']:x for x in d['rows']};print('SEED_OK' if d['source_rows']==45 and len(d['rows'])==45 and r['50035533']['end_date']=='2026-10-12' and r['50048967']['end_date']=='2027-08-04' else 'SEED_BAD')"
  EXPECT: /^SEED_OK$/m
  EVIDENCE: automatic-evidence=v1; definition-sha256=7bb3aeeb54c2e0fc3222efd12dc60d41a14476f7bc86e374bef986d916a62cc2; exit=0; EXPECT=matched; output-sha256=5ca921fcd194d92f6f1d19a26e1d3a5b452b468e5226219cc18b22dfbb556016; output-bytes=8; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-permits; path=82de56a067b7/18 entries

- [x] G9: default mode is dry on a fresh DB
  CHECK: python3 -m unittest tests.test_permits_service.DryDefaultTest 2>&1 | grep -E '^(Ran [0-9]+ tests|OK|FAILED)'
  EXPECT: /^OK$/m
  EVIDENCE: automatic-evidence=v1; definition-sha256=ee48fe39ff5742f390903dedf17351eadcdcd49939fe1b5d8a92bb551d9692d1; exit=0; EXPECT=matched; output-sha256=b5e489fc7005085f6b2c6ef5b991d69ae8e38888620ea74b42b2fdc4d94962c2; output-bytes=25; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-permits; path=82de56a067b7/18 entries

- [x] G10: scope — only OWNS files differ from origin/main (committed or not)
  CHECK: { git diff --name-only origin/main; git ls-files -o --exclude-standard; } | sort -u | grep -vE '^(permits/|tests/test_permits_|tests/permits_fakes.py|tests/fixtures/permits/|bot.py$|requirements.txt$|CLAUDE.md$|\.gitignore$|docs/superpowers/(specs|plans)/2026-10-01-permits)' | wc -l | tr -d ' ' | sed 's/^0$/SCOPE_CLEAN/'
  EXPECT: /^SCOPE_CLEAN$/m
  EVIDENCE: automatic-evidence=v1; definition-sha256=27bda09318f750a3bcd2c0e555ca84d762abd9971b081b82aed1a087498a77ea; exit=0; EXPECT=matched; output-sha256=f22d4d27d3595e4ccffefdf8fadfcf8aee3712698636c6834e199ddabbca948f; output-bytes=12; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-permits; path=82de56a067b7/18 entries

- [x] G11: local smoke — real bot auth + role middleware in front of the package: tab JS served, summary answers with DASHBOARD_TOKEN, refuses without it
  CHECK: python3 permits/tools_smoke.py
  EXPECT: /^SMOKE_OK$/m
  EVIDENCE: automatic-evidence=v1; definition-sha256=ffbb44df2a5cedc07cf03ea7cd58aa383e6a0852a7a42e5f5c582099bad06cc5; exit=0; EXPECT=matched; output-sha256=90b8417774fc079bf86c93a50c4039db8a1ac56e0995227a68066c9fa3d544b7; output-bytes=1253; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-permits; path=82de56a067b7/18 entries

- [x] G13: privacy — no national ID in any file that would be committed (added bot.py lines only), and the xlsx is git-ignored
  CHECK: python3 permits/tools_privacy_scan.py
  EXPECT: /^PRIVACY_OK$/m
  EVIDENCE: automatic-evidence=v1; definition-sha256=1742fc2ded1125f104a8c8e33a78eb62ebb254c350b1840bcf992753a9a92409; exit=0; EXPECT=matched; output-sha256=ba2746d80621683209dcff4780a2950351cdd78b3b5a047362293bbdf2136679; output-bytes=80; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-permits; path=82de56a067b7/18 entries

- [x] G14: real seed matches the oracle row-for-row
  CHECK: python3 -m unittest tests.test_permits_seed_real 2>&1 | grep -E '^(Ran [0-9]+ tests|OK|FAILED)'
  EXPECT: /^OK$/m
  EVIDENCE: automatic-evidence=v1; definition-sha256=762b83ec5cfb85a23ae13c56f4bc071dc60288a9fa676201915a6291691493ca; exit=0; EXPECT=matched; output-sha256=985a19034cd610659e7e1c265cdc6638cd437a46741d78f66edf77949ef05b22; output-bytes=26; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-permits; path=82de56a067b7/18 entries

- [x] G15: Railway gets hijridate, and CLAUDE.md documents the package + fixes trap 2
  CHECK: grep -q "^hijridate~=2.6" requirements.txt && grep -q "the \`permits/\` package" CLAUDE.md && grep -q "NAV_DEF" CLAUDE.md && echo DOCS_OK
  EXPECT: /^DOCS_OK$/m
  EVIDENCE: automatic-evidence=v1; definition-sha256=d8fbf9aa3e5b08a89f0d2174480c47237823b9508ba1d73ba97e77361aa0cd0c; exit=0; EXPECT=matched; output-sha256=6d36de704b81554dfb84505a4da24630d2ffb6dc40ba29dd836d0c858704f7bc; output-bytes=8; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-permits; path=82de56a067b7/18 entries

- [ ] G12: (manual, Faisal after deploy) dashboard tab shows all 45 seeded permits; banner says dry and lists F2 as the ticket that would open; typing «تشغيل» opens the due tickets under «صيانه»; next day 13:00 digest posts once.
  EVIDENCE: pending
