# Gates: RR Desk «طلبات سام» (rrdesk/)

OWNS: rrdesk/**, tools/rr_history_export.py, tests/test_rrdesk_*.py, tests/fixtures/rrdesk/**, docs/rrdesk/**, docs/superpowers/specs/2026-10-24-rrdesk-design.md, docs/superpowers/plans/2026-10-24-rrdesk.md, bot.py, CLAUDE.md, .gitignore

Scope: translation in RR rooms, Sam's requests with owners/SLAs/ladder, misses → ops warnings (dry-run money), KPIs, dashboard tab, debug kit — on branch feat/rrdesk, committed locally, NOT pushed.

- [ ] G0: baseline of the full suite captured on the untouched tree before the first edit
  CHECK: python3 -c "import re;t=open('.unlazy-baseline.txt',encoding='utf-8').read();m=re.search(r'^Ran (\d+) tests',t,re.M);print('BASELINE_OK ran=%s'%m.group(1) if m else 'NO_BASELINE')"
  EXPECT: /^BASELINE_OK ran=\d+$/m

- [ ] G1: bot.py and every rrdesk module compile clean (SyntaxWarning = error)
  CHECK: rm -rf __pycache__ rrdesk/__pycache__ && python3 -W error::SyntaxWarning -m py_compile bot.py rrdesk/*.py tools/rr_history_export.py && echo COMPILED_OK
  EXPECT: /^COMPILED_OK$/m

- [ ] G2: no pyflakes findings in rrdesk/, its tests, finance/ or bot.py (unused imports allowed)
  CHECK: python3 -m pyflakes rrdesk/*.py tests/test_rrdesk_*.py tools/rr_history_export.py bot.py finance/*.py | grep -v "imported but unused" | grep -c . | xargs -I{} sh -c 'test {} -eq 0 && echo FLAKES_OK || echo FLAKES_FOUND_{}'
  EXPECT: /^FLAKES_OK$/m

- [ ] G3: both SPA scripts parse (ERP + the new tab)
  CHECK: node --check finance/static/erp.js && node --check rrdesk/static/rrdesk_tab.js && echo JS_OK
  EXPECT: /^JS_OK$/m

- [ ] G4: every DASHBOARD_HTML script block parses with esprima and every NAV tab id has ar+en labels
  CHECK: python3 -m rrdesk.tools_dash_check
  EXPECT: /^DASH_OK scripts=\d+ tabs=\d+$/m

- [ ] G5: pure engine locks the rules — direction, skip rules, state machine incl. rework + original due, working-minute SLAs across 01:30/11:00, urgent via AirCover days, ladder + no-backlog burst, judge 1/2/3 + week reset, mercy paths, KPIs + «بيانات ناقصة»
  CHECK: python3 -m unittest tests.test_rrdesk_engine 2>&1 | tail -1
  EXPECT: /^OK/m

- [ ] G6: translation — phrase table, cache (second identical message = zero calls), glossary injection, JSON contract, daily cap, timeout → ⚠️ + event without raising, embeds keep numbers/codes/mentions, code-block skip, bot English skipped + bot Arabic translated
  CHECK: python3 -m unittest tests.test_rrdesk_translate 2>&1 | tail -1
  EXPECT: /^OK/m

- [ ] G7: flow — edit/delete mirrored, two overlapping ticks post once, outbox backoff 1/5/15/60, presses found by message id, permission gates + refused presses logged, «سلّمت» proof rule (fails open with a flag), owner order, board edited in place
  CHECK: python3 -m unittest tests.test_rrdesk_flow 2>&1 | tail -1
  EXPECT: /^OK/m

- [ ] G8: warnings — _warn is the only issue_warning call, real ops.db in a temp brain.db, 1 warning → 0.9, dry-run writes ops_dryrun_log only, RR-YYYY-Www never collides, a voided warning restores 1.0
  CHECK: python3 -m unittest tests.test_rrdesk_warn 2>&1 | tail -1
  EXPECT: /^OK/m

- [ ] G9: golden set ≥60 real redacted Sam messages (≥25 requests, ≥25 non-requests) and the precision/threshold table is produced offline
  CHECK: python3 -m unittest tests.test_rrdesk_golden 2>&1 | tail -1
  EXPECT: /^OK/m

- [ ] G10: every replay room produces its expected timeline snapshot
  CHECK: python3 -m unittest tests.test_rrdesk_replay 2>&1 | tail -1
  EXPECT: /^OK/m

- [ ] G11: structure — zero backslashes, no `import bot`, no to_thread, no write verbs in the study tools, ASCII slash names, NAV labels ar+en, no phone/ID/HM code in committed fixtures, CLAUDE.md section present
  CHECK: python3 -m unittest tests.test_rrdesk_structure 2>&1 | tail -1
  EXPECT: /^OK/m

- [ ] G12: bot.py wiring — only existing `_rrdesk.<name>` attributes touched, `_tk_close` still closes when rrdesk raises, the existing RR close-out tests untouched and green
  CHECK: python3 -m unittest tests.test_rrdesk_bot_wiring tests.test_rr_closeout 2>&1 | tail -1
  EXPECT: /^OK/m

- [ ] G13: no NEW failures in the full suite compared with the baseline
  CHECK: python3 -m rrdesk.tools_compare_baseline
  EXPECT: /^NO_NEW_FAILURES/m

- [ ] G14: Musaed selftest still passes
  CHECK: python3 eval_musaed.py --selftest 2>&1 | tail -3
  EXPECT: /(PASS|OK|passed)/i

- [ ] G15: showcase artifacts exist — tab screenshots (desktop + 390 px phone), a replay transcript HTML, the health JSON
  CHECK: python3 -c "import os,json;p='docs/rrdesk/showcase/';need=['tab_desktop_ar.png','tab_phone_ar.png','replay_transcript.html','health.json'];miss=[n for n in need if not os.path.exists(p+n) or os.path.getsize(p+n)<200];json.load(open(p+'health.json'));print('SHOWCASE_OK' if not miss else 'MISSING '+','.join(miss))"
  EXPECT: /^SHOWCASE_OK$/m

- [ ] G16: history study written and redacted, with calibration numbers
  CHECK: python3 -c "t=open('docs/rrdesk/history_study.md',encoding='utf-8').read();ok=all(k in t for k in ('Calibration','Response SLA','Delivery SLA','Silence'));print('STUDY_OK' if ok else 'STUDY_INCOMPLETE')"
  EXPECT: /^STUDY_OK$/m

- [ ] G17: a fresh reviewer subagent reviewed the diff against the non-negotiables; every confirmed finding fixed or listed with a reason
  MANUAL: reviewer output summarised in the final report under «قرارات أخذتها» / review section.
