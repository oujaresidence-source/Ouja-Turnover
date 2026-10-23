# Gates: RR Desk «طلبات سام» (rrdesk/)

OWNS: rrdesk/**, tools/rr_history_export.py, tests/test_rrdesk_*.py, tests/fixtures/rrdesk/**, docs/rrdesk/**, docs/superpowers/specs/2026-10-24-rrdesk-design.md, docs/superpowers/plans/2026-10-24-rrdesk.md, bot.py, CLAUDE.md, .gitignore

Scope: translation in RR rooms, Sam's requests with owners/SLAs/ladder, misses → ops warnings (dry-run money), KPIs, dashboard tab, debug kit — on branch feat/rrdesk, committed locally, NOT pushed.

- [x] G0: baseline of the full suite captured on the untouched tree before the first edit
  CHECK: python3 -c "import re;t=open('.unlazy-baseline.txt',encoding='utf-8').read();m=re.search(r'^Ran (\d+) tests',t,re.M);print('BASELINE_OK ran=%s'%m.group(1) if m else 'NO_BASELINE')"
  EXPECT: /^BASELINE_OK ran=\d+$/m
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-rrdesk; path=985fd6ae610d/17 entries; EXPECT=matched; output-sha256=c3680daf014760b3bc79864daaa6142402a01ec4a57c8ee21c380c408895d329; output-bytes=21

- [x] G1: bot.py and every rrdesk module compile clean (SyntaxWarning = error)
  CHECK: rm -rf __pycache__ rrdesk/__pycache__ && python3 -W error::SyntaxWarning -m py_compile bot.py rrdesk/*.py tools/rr_history_export.py && echo COMPILED_OK
  EXPECT: /^COMPILED_OK$/m
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-rrdesk; path=985fd6ae610d/17 entries; EXPECT=matched; output-sha256=b5f0f591cc9b22d0805079a4d0454effebf2adf2c1be0836adc2e5d5a0034ceb; output-bytes=12

- [x] G2: no pyflakes findings in rrdesk/, its tests, finance/ or bot.py (unused imports allowed)
  CHECK: python3 -m pyflakes rrdesk/*.py tests/test_rrdesk_*.py tools/rr_history_export.py bot.py finance/*.py | grep -v "imported but unused" | grep -c . | xargs -I{} sh -c 'test {} -eq 0 && echo FLAKES_OK || echo FLAKES_FOUND_{}'
  EXPECT: /^FLAKES_OK$/m
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-rrdesk/rrdesk; path=985fd6ae610d/17 entries; EXPECT=matched; output-sha256=bdf66a3da2a8a807d2e3ca1569a43cf649bf63053205475803c1990e2c16983a; output-bytes=228

- [x] G3: both SPA scripts parse (ERP + the new tab)
  CHECK: node --check finance/static/erp.js && node --check rrdesk/static/rrdesk_tab.js && echo JS_OK
  EXPECT: /^JS_OK$/m
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-rrdesk; path=985fd6ae610d/17 entries; EXPECT=matched; output-sha256=cb5bbc09ee6cfa19f42a617de658151521bb40c1007e252da3f72c2bf68e47f5; output-bytes=6

- [x] G4: every DASHBOARD_HTML script block parses with esprima and every NAV tab id has ar+en labels
  CHECK: python3 -m rrdesk.tools_dash_check
  EXPECT: /^DASH_OK scripts=\d+ tabs=\d+$/m
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-rrdesk; path=985fd6ae610d/17 entries; EXPECT=matched; output-sha256=9d218faf63fe09563cd99268ab4451e9ad3b926be90ab6d2289b8e66f323b712; output-bytes=26

- [x] G5: pure engine locks the rules — direction, skip rules, state machine incl. rework + original due, working-minute SLAs across 01:30/11:00, urgent via AirCover days, ladder + no-backlog burst, judge 1/2/3 + week reset, mercy paths, KPIs + «بيانات ناقصة»
  CHECK: python3 -m unittest tests.test_rrdesk_engine 2>&1 | grep -E "^(OK|FAILED)"
  EXPECT: /^OK/m
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-rrdesk; path=985fd6ae610d/17 entries; EXPECT=matched; output-sha256=a12b7cb43c9d9134b5bb1b35e9096b66775d9e92e7611d1cc92b02edd6782a87; output-bytes=3

- [x] G6: translation — phrase table, cache (second identical message = zero calls), glossary injection, JSON contract, daily cap, timeout → ⚠️ + event without raising, embeds keep numbers/codes/mentions, code-block skip, bot English skipped + bot Arabic translated
  CHECK: python3 -m unittest tests.test_rrdesk_translate 2>&1 | grep -E "^(OK|FAILED)"
  EXPECT: /^OK/m
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-rrdesk; path=985fd6ae610d/17 entries; EXPECT=matched; output-sha256=a12b7cb43c9d9134b5bb1b35e9096b66775d9e92e7611d1cc92b02edd6782a87; output-bytes=3

- [x] G7: flow — edit/delete mirrored, two overlapping ticks post once, outbox backoff 1/5/15/60, presses found by message id, permission gates + refused presses logged, «سلّمت» proof rule (fails open with a flag), owner order, board edited in place
  CHECK: python3 -m unittest tests.test_rrdesk_flow 2>&1 | grep -E "^(OK|FAILED)"
  EXPECT: /^OK/m
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-rrdesk; path=985fd6ae610d/17 entries; EXPECT=matched; output-sha256=a12b7cb43c9d9134b5bb1b35e9096b66775d9e92e7611d1cc92b02edd6782a87; output-bytes=3

- [x] G8: warnings — _warn is the only issue_warning call, real ops.db in a temp brain.db, 1 warning → 0.9, dry-run writes ops_dryrun_log only, RR-YYYY-Www never collides, a voided warning restores 1.0
  CHECK: python3 -m unittest tests.test_rrdesk_warn 2>&1 | grep -E "^(OK|FAILED)"
  EXPECT: /^OK/m
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-rrdesk; path=985fd6ae610d/17 entries; EXPECT=matched; output-sha256=a12b7cb43c9d9134b5bb1b35e9096b66775d9e92e7611d1cc92b02edd6782a87; output-bytes=3

- [x] G9: golden set ≥60 real redacted Sam messages (≥25 requests, ≥25 non-requests) and the precision/threshold table is produced offline
  CHECK: python3 -m unittest tests.test_rrdesk_golden 2>&1 | grep -E "^(OK|FAILED)"
  EXPECT: /^OK/m
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-rrdesk; path=985fd6ae610d/17 entries; EXPECT=matched; output-sha256=faa488b7581ae7bfc00cd12d751f871753558c933945bfa643ce25de502127c3; output-bytes=15

- [x] G10: every replay room produces its expected timeline snapshot
  CHECK: python3 -m unittest tests.test_rrdesk_replay 2>&1 | grep -E "^(OK|FAILED)"
  EXPECT: /^OK/m
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-rrdesk; path=985fd6ae610d/17 entries; EXPECT=matched; output-sha256=a12b7cb43c9d9134b5bb1b35e9096b66775d9e92e7611d1cc92b02edd6782a87; output-bytes=3

- [x] G11: structure — zero backslashes, no `import bot`, no to_thread, no write verbs in the study tools, ASCII slash names, NAV labels ar+en, no phone/ID/HM code in committed fixtures, CLAUDE.md section present
  CHECK: python3 -m unittest tests.test_rrdesk_structure 2>&1 | grep -E "^(OK|FAILED)"
  EXPECT: /^OK/m
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-rrdesk; path=985fd6ae610d/17 entries; EXPECT=matched; output-sha256=a12b7cb43c9d9134b5bb1b35e9096b66775d9e92e7611d1cc92b02edd6782a87; output-bytes=3

- [x] G12: bot.py wiring — only existing `_rrdesk.<name>` attributes touched, `_tk_close` still closes when rrdesk raises, the existing RR close-out tests untouched and green
  CHECK: python3 -m unittest tests.test_rrdesk_bot_wiring tests.test_rr_closeout 2>&1 | grep -E "^(OK|FAILED)"
  EXPECT: /^OK/m
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-rrdesk; path=985fd6ae610d/17 entries; EXPECT=matched; output-sha256=a12b7cb43c9d9134b5bb1b35e9096b66775d9e92e7611d1cc92b02edd6782a87; output-bytes=3

- [x] G13: no NEW failures in the full suite compared with the baseline
  CHECK: python3 -m rrdesk.tools_compare_baseline
  EXPECT: /^NO_NEW_FAILURES/m
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-rrdesk; path=985fd6ae610d/17 entries; EXPECT=matched; output-sha256=dbf3a84f62ba3aee8943226daadf7ada18efdfe58c42bb94c18f6717ee3d7fd9; output-bytes=43

- [x] G14: Musaed selftest still passes
  CHECK: python3 eval_musaed.py --selftest 2>&1 | tail -3
  EXPECT: /(PASS|OK|passed)/i
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-rrdesk; path=985fd6ae610d/17 entries; EXPECT=matched; output-sha256=882f634676dd095379208467579ed665f29c1871dc25f64b819eb1cd4087dcde; output-bytes=103

- [x] G15: showcase artifacts exist — tab screenshots (desktop + 390 px phone), a replay transcript HTML, the health JSON
  CHECK: python3 -c "import os,json;p='docs/rrdesk/showcase/';need=['tab_desktop_ar.png','tab_phone_ar.png','replay_transcript.html','health.json'];miss=[n for n in need if not os.path.exists(p+n) or os.path.getsize(p+n)<200];json.load(open(p+'health.json'));print('SHOWCASE_OK' if not miss else 'MISSING '+','.join(miss))"
  EXPECT: /^SHOWCASE_OK$/m
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-rrdesk; path=985fd6ae610d/17 entries; EXPECT=matched; output-sha256=8bdad0f5a5b52e5010e8ebafb8d27b4d3423cd604c239f721802a0fe0e2a1b00; output-bytes=12

- [x] G16: history study written and redacted, with calibration numbers
  CHECK: python3 -c "t=open('docs/rrdesk/history_study.md',encoding='utf-8').read();ok=all(k in t for k in ('Calibration','Response SLA','Delivery SLA','Silence'));print('STUDY_OK' if ok else 'STUDY_INCOMPLETE')"
  EXPECT: /^STUDY_OK$/m
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-rrdesk; path=985fd6ae610d/17 entries; EXPECT=matched; output-sha256=ffb8c718b1b46897a9b3cb0056d6ef72d1aa53e2b935974dfce52eff9c857eef; output-bytes=9

- [x] G17: a fresh reviewer subagent reviewed the diff against the non-negotiables; every confirmed finding fixed or listed with a reason
  MANUAL: reviewer output summarised in the final report under «قرارات أخذتها» / review section.
  EVIDENCE: fresh reviewer pass 1 (diff + non-negotiables only): 11 findings + 6 minor, all fixed in 80a1d40. Re-check pass on 80a1d40: 8 fixed, 3 partial, 3 new; fixed in 0e7b47f (outsider asks unowned, edit retry vs once-marker, unknown rooms never closed). Kept on purpose, with reasons: a crash between a Discord send and its done-record can re-post after the 30-min takeover (residual, rare); /rrdesk/health shows switches + detection mode (the brief lists switches in health; no names or text); cap hit = explicit-only (the brief's rule); a late-opened request counts ANY earlier team message as acknowledgement (lenient, never unfair).
