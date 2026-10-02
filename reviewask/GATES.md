# Gates: Review Push «رفع التقييم» (reviewask/)

OWNS: reviewask/**, tests/test_reviewask_*.py, bot.py, ops_tidy_rules.py, tests/test_ops_tidy_rules.py, CLAUDE.md, docs/superpowers/specs/2026-10-03-review-push-design.md, docs/superpowers/plans/2026-10-03-review-push.md

Scope: the owner-approved Review Push (spec 2026-10-03-review-push-design.md) — weak-apartment detection, one Discord room per qualifying checkout, WhatsApp + call ladder with text-only buttons, review-origin maintenance tickets, owner-edited templates, /تقييمات-بكرة, Checkout-Watch-style tracking, 7-day deletion of closed review rooms — shipped OFF, on a branch, not pushed.

- [x] G0: baseline of the full suite captured on the untouched tree BEFORE the first edit
  CHECK: python3 -c "import re;t=open('.unlazy-baseline-rv.txt',encoding='utf-8').read();m=re.search(r'^Ran (\d+) tests',t,re.M);print('BASELINE_OK ran=%s'%m.group(1) if m else 'NO_BASELINE')"
  EXPECT: /^BASELINE_OK ran=\d+$/m
  EVIDENCE: automatic-evidence=v1; definition-sha256=6544d149ca28f1135c5a7e2f24eb0e089dba87343a8019792ccd634821818bd9; exit=0; EXPECT=matched; output-sha256=b5661418221baad4fbd1b7f3337ff4a11a54a11c22f80e80e9fe32df31a3d746; output-bytes=21; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-review; path=82de56a067b7/18 entries

- [x] G1: bot.py and every reviewask module compile clean (SyntaxWarning = error)
  CHECK: rm -rf __pycache__ reviewask/__pycache__ && python3 -W error::SyntaxWarning -m py_compile bot.py reviewask/*.py && echo COMPILED_OK
  EXPECT: /^COMPILED_OK$/m
  EVIDENCE: automatic-evidence=v1; definition-sha256=4b05ab48faf978ae37d47b09f885baa27718ed7599f45b8ecd53bbaa4d526646; exit=0; EXPECT=matched; output-sha256=b5f0f591cc9b22d0805079a4d0454effebf2adf2c1be0836adc2e5d5a0034ceb; output-bytes=12; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-review; path=82de56a067b7/18 entries

- [x] G2: no pyflakes findings in reviewask/ or its tests, none new in bot.py (unused imports allowed)
  CHECK: python3 -m pyflakes reviewask/*.py tests/test_reviewask_*.py bot.py | grep -v "imported but unused" | grep -c . | xargs -I{} sh -c 'test {} -eq 0 && echo FLAKES_OK || echo FLAKES_FOUND_{}'
  EXPECT: /^FLAKES_OK$/m
  EVIDENCE: automatic-evidence=v1; definition-sha256=cd1aa3fb768952d32d677ed15a2fb5b585ccdea3a88052e7298260fda0e9883e; exit=0; EXPECT=matched; output-sha256=b87af89f8e581ce51e880b13a0944add58fc17186928841bf011e5c13189b4ab; output-bytes=10; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-review; path=82de56a067b7/18 entries

- [x] G3: pure engine locks every owner rule — 4.75 in/out, <3 reviews, reviews_needed: (n=10,R=90)→11, (47,415)→64, (4,38)→1, call_time (20:00 / 20:45 May–Aug / 21:30 Ramadan / env override), max 2 calls, staff miss keeps the attempt, quiet 22:00–13:00, day-14 expiry, language by phone, unknown placeholder survives
  CHECK: python3 -m unittest tests.test_reviewask_engine 2>&1 | tail -1
  EXPECT: /^OK/m
  EVIDENCE: automatic-evidence=v1; definition-sha256=be0e0b562a49f8f2ee7286a73743640adc9440c0f9c07e64442a69d5dfc867b4; exit=0; EXPECT=matched; output-sha256=a12b7cb43c9d9134b5bb1b35e9096b66775d9e92e7611d1cc92b02edd6782a87; output-bytes=3; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-review; path=82de56a067b7/18 entries

- [x] G4: flow + db — one room per reservation across 3 overlapping ticks, first-final-wins, a matched review closes from any open state, cancellation closes, /rv/<token> logs wa_opened and 302s to wa.me with the rendered template
  CHECK: python3 -m unittest tests.test_reviewask_flow 2>&1 | tail -1
  EXPECT: /^OK/m
  EVIDENCE: automatic-evidence=v1; definition-sha256=d458af0adb4ebf2bf5be8e317b071fd553f0fe51e6c9b53bd536d3ca12544cb4; exit=0; EXPECT=matched; output-sha256=a12b7cb43c9d9134b5bb1b35e9096b66775d9e92e7611d1cc92b02edd6782a87; output-bytes=3; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-review; path=82de56a067b7/18 entries

- [x] G5: deletion safety — only rv rooms closed ≥7 days whose topic carries the same reservation id are deleted; a wrong topic is refused; the transcript row exists before delete; "couldn't fetch" is never "deleted"
  CHECK: python3 -m unittest tests.test_reviewask_delete 2>&1 | tail -1
  EXPECT: /^OK/m
  EVIDENCE: automatic-evidence=v1; definition-sha256=68c00457b4a2ba93083a1e9e1c7ff9fb48d9de02dfc2644e11211b9883323abf; exit=0; EXPECT=matched; output-sha256=a12b7cb43c9d9134b5bb1b35e9096b66775d9e92e7611d1cc92b02edd6782a87; output-bytes=3; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-review; path=82de56a067b7/18 entries

- [x] G6: bot.py integration — «عنده ملاحظة» opens a maintenance room whose title starts «من مكالمة تقييم», source=review, field «المصدر», link back; existing _maint_open_ticket callers unchanged; commands registered; NAV labels in BOTH ar and en
  CHECK: python3 -m unittest tests.test_reviewask_bot 2>&1 | tail -1
  EXPECT: /^OK/m
  EVIDENCE: automatic-evidence=v1; definition-sha256=3bbf624b8ec5df992d6643374cdfc00f4b0bf7f46ea265a1a4b7ad3ab475c39f; exit=0; EXPECT=matched; output-sha256=a12b7cb43c9d9134b5bb1b35e9096b66775d9e92e7611d1cc92b02edd6782a87; output-bytes=3; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-review; path=82de56a067b7/18 entries

- [x] G7: structure — every button label in reviewask/ has no emoji, no `import bot`, no asyncio.to_thread, zero backslashes in reviewask/*.py, no discount text hard-coded in .py, channel.delete called only inside sweep_closed
  CHECK: python3 -m unittest tests.test_reviewask_structure 2>&1 | tail -1
  EXPECT: /^OK/m
  EVIDENCE: automatic-evidence=v1; definition-sha256=111ea518d06e0e02fc0455643b1e1cce89b4faab900e7bb9b3a1dcf651854572; exit=0; EXPECT=matched; output-sha256=a12b7cb43c9d9134b5bb1b35e9096b66775d9e92e7611d1cc92b02edd6782a87; output-bytes=3; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-review; path=82de56a067b7/18 entries

- [x] G8: ops_tidy never archives, locks or renames an ouja-rv: room, and its existing 2026-10-02 decisions are unchanged
  CHECK: python3 -m unittest tests.test_ops_tidy_rules 2>&1 | tail -1
  EXPECT: /^OK/m
  EVIDENCE: automatic-evidence=v1; definition-sha256=f060d675b9f305d7b038cc9373cba89147c19496e7cf4e22e3786fb923e2d474; exit=0; EXPECT=matched; output-sha256=a12b7cb43c9d9134b5bb1b35e9096b66775d9e92e7611d1cc92b02edd6782a87; output-bytes=3; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-review; path=82de56a067b7/18 entries

- [x] G9: full suite has no failure that is not already in the baseline
  CHECK: python3 -m unittest discover -s tests -p "test_*.py" 2>&1 | python3 -c "import sys,re;t=sys.stdin.read();b=open('.unlazy-baseline-rv.txt',encoding='utf-8').read();f=lambda s:set(re.findall(r'^(?:FAIL|ERROR): (\S+ \(\S+\))',s,re.M));new=f(t)-f(b);ran=re.search(r'^Ran (\d+) tests',t,re.M);print('NO_NEW_FAILURES ran=%s'%ran.group(1) if ran and not new else 'NEW_FAILURES %s'%sorted(new))"
  EXPECT: /^NO_NEW_FAILURES ran=\d+$/m
  EVIDENCE: automatic-evidence=v1; definition-sha256=0e0199c4b5dde8afc82f29832b8cb833074fbfe5098691825e70fac68c658a45; exit=0; EXPECT=matched; output-sha256=94ff088b74f7ccf2784ecfa47712cd515c4ba65df7fa7d71354dcd7616cb1c76; output-bytes=25; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-review; path=82de56a067b7/18 entries

- [x] G10: dashboard still logs in — every DASHBOARD_HTML <script> parses and the tab JS passes node --check
  CHECK: node --check reviewask/static/reviewask_tab.js && python3 -c "import bot,esprima,re;[esprima.parseScript(j) for j in re.findall(r'<script>(.*?)</script>',bot.DASHBOARD_HTML,re.S)];print('JS_OK')"
  EXPECT: /^JS_OK$/m
  EVIDENCE: automatic-evidence=v1; definition-sha256=2a1d8231f48a04ad147689c9836a391f9e9dffa42efa94a944ebc4865dc347d0; exit=0; EXPECT=matched; output-sha256=0c5181316ffe9c6291f4f82342f9399b4cceabd5f160ea85afd7840578f58864; output-bytes=1229; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-review; path=82de56a067b7/18 entries

- [x] G11: musaed selftest unaffected
  CHECK: python3 eval_musaed.py --selftest 2>&1 | tail -3
  EXPECT: /SELFTEST PASSED/i
  EVIDENCE: automatic-evidence=v1; definition-sha256=1ab2c97f90d62b623d865a282d470c6db63915a8cc4593c7905fa6d2cd88a69a; exit=0; EXPECT=matched; output-sha256=882f634676dd095379208467579ed665f29c1871dc25f64b819eb1cd4087dcde; output-bytes=103; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-review; path=82de56a067b7/18 entries

- [ ] G12: live Hostaway review `type` / `channelName` values were printed and the guest-to-host + Airbnb filter in engine matches them (record the values here)
  EVIDENCE: pending

- [ ] G13: owner dry run — with REVIEWASK_LIVE=0, /تقييمات-بكرة replied with the would-open list and skip reasons for tomorrow; owner confirmed the list looks right before /تقييمات-تشغيل
  EVIDENCE: pending

- [ ] G14: on a real phone, «فتح واتساب» opened WhatsApp on the test number with the owner's saved message fully typed (Arabic and English), and the review link landed on Airbnb's reviews page
  EVIDENCE: pending

- [x] G15: work sits on branch feat/review-push, committed, NOT on the remote — owner says when to push
  CHECK: test "$(git rev-parse --abbrev-ref HEAD)" = feat/review-push && test -z "$(git status --porcelain -- reviewask tests bot.py)" && test -z "$(git ls-remote --heads origin feat/review-push)" && echo BRANCH_LOCAL_OK
  EXPECT: /^BRANCH_LOCAL_OK$/m
  EVIDENCE: automatic-evidence=v1; definition-sha256=1111868dcf7da30563cf32877e1d7b16d47a4810b3da805ea73f5446d5ee4dc7; exit=0; EXPECT=matched; output-sha256=0d7b8b0db6c7e9050506875ff1cc31bc85df51b32d192c8f1c0820baccce2f6c; output-bytes=16; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-review; path=82de56a067b7/18 entries
