# Gates: «اجتماع المالك» Owner Meeting Room (owner_meet/)

OWNS: owner_meet/**, tests/test_owner_meet_*.py, tests/fixtures/owner_meet/**, docs/owner_meet/**, bot.py, docs/superpowers/specs/2026-10-06-owner-meet-design.md, docs/superpowers/plans/2026-10-06-owner-meet.md, CLAUDE.md

Scope: the owner-approved Owner Meeting Room (spec 2026-10-06-owner-meet-design.md). A frozen per-apartment snapshot, a 16:9 presentation plus a presenter window, a meeting record, a read-only owner link plus PDF, and the Airbnb report importer. Built on branch feat/owner-meet in worktree ~/ouja-wt-meet. Never pushed without Faisal's word. bot.py edits are additive only. The money math and `_maint_open_ticket` stay byte-for-byte unchanged.

Slice map: G0, G29 = S0 · G1, G2, G4–G8, G21, G22, G30 = S1 · G3, G13, G15, G16, G17, G23 = S2 · G11, G12, G24 = S3 · G9, G10, G25 = S4 · G14, G18, G19, G26, G31 = S5 · G20, G27 = S6 · G28 = every push. The routine gates G1–G5 and G6/G7 are re-run at the end of EVERY slice.

- [x] G0: baseline of the full suite captured on the untouched tree BEFORE the first edit
  CHECK: python3 -c "import re;t=open('.unlazy-baseline-meet.txt',encoding='utf-8').read();m=re.search(r'^Ran (\d+) tests',t,re.M);print('BASELINE_OK ran=%s'%m.group(1) if m else 'NO_BASELINE')"
  EXPECT: /^BASELINE_OK ran=\d+$/m
  EVIDENCE: automatic-evidence=v1; definition-sha256=69639b5e58565c56067e36d73f41bbcb7697153255b0c23cf193a29297da013c; exit=0; EXPECT=matched; output-sha256=9725baa2335e6f3f000b4fcecaf52f9a7fe20aee48c5a1af564a8c1dd7e9ae5c; output-bytes=21; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-meet; path=82de56a067b7/18 entries

- [x] G1: bot.py and every owner_meet module compile clean (SyntaxWarning = error)
  CHECK: rm -rf __pycache__ owner_meet/__pycache__ && python3 -W error::SyntaxWarning -m py_compile bot.py owner_meet/*.py && echo COMPILED_OK
  EXPECT: /^COMPILED_OK$/m
  EVIDENCE: automatic-evidence=v1; definition-sha256=6d62c6a3965a7825b912fc44e68508eb40d08404bf1b17f5f76451a978bf4f6d; exit=0; EXPECT=matched; output-sha256=b5f0f591cc9b22d0805079a4d0454effebf2adf2c1be0836adc2e5d5a0034ceb; output-bytes=12; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-meet; path=82de56a067b7/18 entries

- [x] G2: no pyflakes findings in owner_meet/ or its tests, none in bot.py or finance/ (unused imports allowed)
  CHECK: python3 -m pyflakes owner_meet/*.py tests/test_owner_meet_*.py bot.py finance/*.py | grep -v "imported but unused" | grep -c . | xargs -I{} sh -c 'test {} -eq 0 && echo FLAKES_OK || echo FLAKES_FOUND_{}'
  EXPECT: /^FLAKES_OK$/m
  EVIDENCE: automatic-evidence=v1; definition-sha256=72d520303ea4bf937688490bfccfb5ff12718493439e3019457b0202c253d035; exit=0; EXPECT=matched; output-sha256=b87af89f8e581ce51e880b13a0944add58fc17186928841bf011e5c13189b4ab; output-bytes=10; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-meet; path=82de56a067b7/18 entries

- [x] G3: every package JS file and the ERP SPA parse (one bad token = dead page)
  CHECK: for f in owner_meet/static/*.js finance/static/erp.js; do node --check "$f" || exit 1; done && echo JS_FILES_OK
  EXPECT: /^JS_FILES_OK$/m
  EVIDENCE: automatic-evidence=v1; definition-sha256=a78ddab1b1a779b6c010696677535856085d91712476afd70a33aa7f3b24018e; exit=0; EXPECT=matched; output-sha256=29c6aa2e2681ea06f46076474df26d961903e88635cfb971ccdb2640fd9552ff; output-bytes=12; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-meet; path=82de56a067b7/18 entries

- [x] G4: dashboard still logs in — every DASHBOARD_HTML <script> parses with esprima
  CHECK: mkdir -p /tmp/ouja-meet-g4 && STATE_DIR=/tmp/ouja-meet-g4 python3 -c "import bot,esprima,re;[esprima.parseScript(j) for j in re.findall(r'<script>(.*?)</script>',bot.DASHBOARD_HTML,re.S)];print('DASH_JS_OK')"
  EXPECT: /^DASH_JS_OK$/m
  EVIDENCE: automatic-evidence=v1; definition-sha256=6ce16c9e6ab0a5f22a940d7a5e429b933c4552a27ac6ae38fb456a2ef506c42d; exit=0; EXPECT=matched; output-sha256=d00b56c99ae46f7df7ef37400c1f23b860a6e61f410423d703c08fafb55ed915; output-bytes=847; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-meet; path=82de56a067b7/18 entries

- [x] G5: full suite has no failure that is not already in the baseline (main carries 3 date-dependent failures)
  CHECK: python3 -m unittest discover -s tests -p "test_*.py" 2>&1 | python3 -c "import sys,re;t=sys.stdin.read();b=open('.unlazy-baseline-meet.txt',encoding='utf-8').read();f=lambda s:set(re.findall(r'^(?:FAIL|ERROR): (\S+ \(\S+\))',s,re.M));new=f(t)-f(b);ran=re.search(r'^Ran (\d+) tests',t,re.M);print('NO_NEW_FAILURES ran=%s'%ran.group(1) if ran and not new else 'NEW_FAILURES %s'%sorted(new))"
  EXPECT: /^NO_NEW_FAILURES ran=\d+$/m
  EVIDENCE: automatic-evidence=v1; definition-sha256=b7ceecdd2500bae5e8aff6d4016837216202b8c05f66b2b9aa332a3d06b0edae; exit=0; EXPECT=matched; output-sha256=cffc909ee79e815109e11d286736c670cfb0d7fe5e931729df9d1073c679fb0f; output-bytes=25; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-meet; path=82de56a067b7/18 entries

- [x] G6: structure — no `import bot`, no to_thread / run_in_executor, zero backslashes in every owner_meet .py and .js, py3.9-parseable, no «مثال توضيحي», no scheduler or automatic send, never get_reservations_cached; bot.py carries the import guard + wire/bootstrap block and caps that wrap _owner_month_report / unit_slice / fetch_reservations_window_checked and never create a portal token
  CHECK: python3 -m unittest tests.test_owner_meet_structure 2>&1 | grep -E "^(OK|FAILED)" | tail -1
  EXPECT: /^OK/m
  EVIDENCE: automatic-evidence=v1; definition-sha256=7d792d48e0fe723ea92a73bc5adbdf119fb6a7ff65666b996870304b17a76a12; exit=0; EXPECT=matched; output-sha256=a12b7cb43c9d9134b5bb1b35e9096b66775d9e92e7611d1cc92b02edd6782a87; output-bytes=3; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-meet; path=82de56a067b7/18 entries

- [x] G7: the money math and the maintenance-ticket opener are byte-for-byte unchanged vs origin/main (compute_owner_report, build_owner_report, _finance_aggregate, _owner_month_report_compute, _maint_open_ticket, finance/owners.py)
  CHECK: python3 -c "import subprocess,re;g=lambda p:subprocess.run(['git','show','origin/main:'+p],capture_output=True,text=True).stdout;w=lambda p:open(p,encoding='utf-8').read();fn=lambda s,n:(lambda m:s[m.start():s.find(chr(10)+'def ',m.end())] if m else None)(re.search(r'^(async )?def '+n+r'\(',s,re.M));ob,nb=g('bot.py'),w('bot.py');bad=[n for n in ('compute_owner_report','build_owner_report','_finance_aggregate','_owner_month_report_compute','_maint_open_ticket') if fn(ob,n) is None or fn(ob,n)!=fn(nb,n)];bad+=['finance/owners.py'] if g('finance/owners.py')!=w('finance/owners.py') else [];print('MONEY_UNTOUCHED' if not bad else 'CHANGED %s'%bad)"
  EXPECT: /^MONEY_UNTOUCHED$/m
  EVIDENCE: automatic-evidence=v1; definition-sha256=9b57036f0b17fb942c3e34a39d4637ebe1b4a0ee3e977ee6269aae25f322f7ef; exit=0; EXPECT=matched; output-sha256=f6a18c8daaf9e3fe019f7047f689773394b072293f13fb1391dbbae1b1c930ad; output-bytes=16; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-meet; path=82de56a067b7/18 entries

- [x] G8: M1/M2/M4 — the meeting's owner net equals the hand-summed owner_net of the real statement path to the halala for 1, 3 and 12 months (owner level and unit level), the management % comes from terms_on (a changed term changes the label), the waterfall rows reconcile to owner_net or fall back, and a degraded month blocks send
  CHECK: python3 -m unittest tests.test_owner_meet_money 2>&1 | grep -E "^(OK|FAILED)" | tail -1
  EXPECT: /^OK/m
  EVIDENCE: automatic-evidence=v1; definition-sha256=176a0445c8a3203cc746555d0d938edc025fe9eb0cd4df03a12b5782cff27840; exit=0; EXPECT=matched; output-sha256=a12b7cb43c9d9134b5bb1b35e9096b66775d9e92e7611d1cc92b02edd6782a87; output-bytes=3; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-meet; path=82de56a067b7/18 entries

- [x] G9: action engine — headline rule order, every action trigger on synthetic data (rate, new, ctr, page, pace, maint_open, rr_open, permit, floor, test-only-when-confirmed), forecast base / seasonal / target math, +15% uplift cap, <3 full months → no forecast, discount-stack warning above the ceiling
  CHECK: python3 -m unittest tests.test_owner_meet_actions 2>&1 | grep -E "^(OK|FAILED)" | tail -1
  EXPECT: /^OK/m
  EVIDENCE: automatic-evidence=v1; definition-sha256=5f28d0c4f577520390cce34541290241f4b201db6b8c6942577f3bbce7f27326; exit=0; EXPECT=matched; output-sha256=a12b7cb43c9d9134b5bb1b35e9096b66775d9e92e7611d1cc92b02edd6782a87; output-bytes=3; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-meet; path=82de56a067b7/18 entries

- [x] G10: Airbnb importer — the real 2026-10-04 TSV gives 42 rows, data_as_of 2026-10-04, no rank 8 (no crash), 8 blank 14-day-availability values stored as None, Σ GBV USD 896,734, median rating 4.815, 15 below 4.75; XLSX round-trip gives identical rows; a malformed file is refused with the Arabic message; a second import never overwrites the first; unmapped rows are listed, not dropped
  CHECK: python3 -m unittest tests.test_owner_meet_import 2>&1 | grep -E "^(OK|FAILED)" | tail -1
  EXPECT: /^OK/m
  EVIDENCE: automatic-evidence=v1; definition-sha256=526a407bf6407d09c4fc10db7b983b405db4f9931d67feda8fef3e95e2e217e7; exit=0; EXPECT=matched; output-sha256=a12b7cb43c9d9134b5bb1b35e9096b66775d9e92e7611d1cc92b02edd6782a87; output-bytes=3; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-meet; path=82de56a067b7/18 entries

- [x] G11: ops joins — maintenance deduped by dash_id, cost from _tickets/linked expense, hours to close, source never a person; RR outcome chips equal _rr_outcome for every closeout fixture, AirCover deadline = departure + 14 days for open claims only, RR without lid matched by unit name; 0/empty-score reviews ignored; private_review never in the owner part; reviewask follow-up shown as «تابعنا مع الضيف»; price actions exclude dry entries
  CHECK: python3 -m unittest tests.test_owner_meet_ops 2>&1 | grep -E "^(OK|FAILED)" | tail -1
  EXPECT: /^OK/m
  EVIDENCE: automatic-evidence=v1; definition-sha256=83d2c5b0b0bfc69e97fdda908239977cb5586e0bc2ff56ac737bd78f96d4f914; exit=0; EXPECT=matched; output-sha256=a12b7cb43c9d9134b5bb1b35e9096b66775d9e92e7611d1cc92b02edd6782a87; output-bytes=3; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-meet; path=82de56a067b7/18 entries

- [x] G12: privacy R1–R6 — the presentation HTML source (the owner surface built so far) for the planted fixture snapshots contains no listing count / rank / n=, no other fixture owner or unit name, no fixture guest full name, no HM-code, no 05xxxxxxxx / 9665xxxxxxxx, no email, no staff name, no internal-economics words, no «مثال»; AND the same scanner flags each of these when planted (positive control)
  CHECK: python3 -m unittest tests.test_owner_meet_privacy 2>&1 | grep -E "^(OK|FAILED)" | tail -1
  EXPECT: /^OK/m
  EVIDENCE: automatic-evidence=v1; definition-sha256=6dc1280eeb7e87b7a11494d49935fd45c5102e33b822400fedbc4fcfe61f45df; exit=0; EXPECT=matched; output-sha256=a12b7cb43c9d9134b5bb1b35e9096b66775d9e92e7611d1cc92b02edd6782a87; output-bytes=3; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-meet; path=82de56a067b7/18 entries

- [x] G13: dashboard-side routes — every /api/meet/* route is behind «meet» for read AND write and nothing is exempt; the only non-/api routes are /meet/{id}, /meet/{id}/notes, /meet/static/{name}, /meet/font/{name}; pages 302 to /dashboard#meet without login and 403 without the permission; static + font doors serve their allow-list only; OWNER_MEET_ENABLED=0 registers no route; the cursor round-trips with a rising sequence; every handler hands work to HOST.web_thread (never to_thread); a new non-admin user never receives «meet» from a role default
  CHECK: python3 -m unittest tests.test_owner_meet_routes 2>&1 | grep -E "^(OK|FAILED)" | tail -1
  EXPECT: /^OK/m
  EVIDENCE: automatic-evidence=v1; definition-sha256=a051cb84999bf82d0284b4c216cd114fedcb996f713359c793e7083cc2f331da; exit=0; EXPECT=matched; output-sha256=a12b7cb43c9d9134b5bb1b35e9096b66775d9e92e7611d1cc92b02edd6782a87; output-bytes=3; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-meet; path=82de56a067b7/18 entries

- [x] G14: meeting record — a frozen snapshot has no update path (write attempt refused), sha256 matches the stored JSON, reopen needs admin + non-empty reason and creates version+1, links keep their version, chapter 0 of the next meeting lists every previous commitment with status and evidence (a linked closed ticket → done with its close date)
  CHECK: python3 -m unittest tests.test_owner_meet_record 2>&1 | grep -E "^(OK|FAILED)" | tail -1
  EXPECT: /^OK/m
  EVIDENCE: automatic-evidence=v1; definition-sha256=368e0456c4f0c41a607627f8cefd0074593311ebbea8e47a5350af73f167cdfe; exit=0; EXPECT=matched; output-sha256=a12b7cb43c9d9134b5bb1b35e9096b66775d9e92e7611d1cc92b02edd6782a87; output-bytes=3; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-meet; path=82de56a067b7/18 entries

- [x] G15: dashboard tab — NAV id «meet» labelled in BOTH labels.ar and labels.en (no "undefined"), ("/api/meet/","meet") in _ROLE_READ_RULES AND _ROLE_WRITE_RULES, view_meet appears exactly once without class="view on", the loader stub has zero backslashes and ≤ 15 non-blank lines, __OWNER_MEET_JS_V__ is replaced by a number, go() routes «meet», «meet» sits in cat_finance next to ownrep, the tab JS has no onclick=
  CHECK: python3 -m unittest tests.test_owner_meet_dashboard 2>&1 | grep -E "^(OK|FAILED)" | tail -1
  EXPECT: /^OK/m
  EVIDENCE: automatic-evidence=v1; definition-sha256=799c3421f63a163ef1b330171c624bed411cb97e344151722b57d08ee5df9f45; exit=0; EXPECT=matched; output-sha256=a12b7cb43c9d9134b5bb1b35e9096b66775d9e92e7611d1cc92b02edd6782a87; output-bytes=3; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-meet; path=82de56a067b7/18 entries

- [x] G16: charts — every SVG renderer is deterministic (same input → same bytes, golden files), zero-based bars, no dual axis, each chart carries <title> and a text alternative, Arabic text nodes carry direction="rtl", peer charts draw bands never one mark per peer
  CHECK: python3 -m unittest tests.test_owner_meet_charts 2>&1 | grep -E "^(OK|FAILED)" | tail -1
  EXPECT: /^OK/m
  EVIDENCE: automatic-evidence=v1; definition-sha256=176adefe01c7ca241ea537d96c3f27d2101dbda5419984164f25e1816c2f7a1e; exit=0; EXPECT=matched; output-sha256=a12b7cb43c9d9134b5bb1b35e9096b66775d9e92e7611d1cc92b02edd6782a87; output-bytes=3; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-meet; path=82de56a067b7/18 entries

- [x] G17: the presentation renders from a frozen 12-month fixture snapshot in under 1 second (render only, no data access)
  CHECK: python3 -m unittest tests.test_owner_meet_render 2>&1 | grep -E "^(OK|FAILED)" | tail -1
  EXPECT: /^OK/m
  EVIDENCE: automatic-evidence=v1; definition-sha256=808ff45b9a82b2af326ea0717f96362060eb616ca15137e609cd68a7d6b1bd75; exit=0; EXPECT=matched; output-sha256=a12b7cb43c9d9134b5bb1b35e9096b66775d9e92e7611d1cc92b02edd6782a87; output-bytes=3; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-meet; path=82de56a067b7/18 entries

- [x] G18: layout audit in a real Chromium — every chapter at 1280×720 has no overflowing or clipped text node, the owner link at 390 px has no horizontal scroll (scrollWidth ≤ clientWidth)
  CHECK: "${OUJA_PY:-python3}" owner_meet/tools_layout_audit.py --fixture tests/fixtures/owner_meet/snapshot_full.json
  EXPECT: /^LAYOUT_OK chapters=\d+ overflow=0 phone_hscroll=0$/m
  EVIDENCE: automatic-evidence=v1; definition-sha256=df0f9bc8f2460a6d3fe581fcfd475da10ecefc2cf919e2291ff7797d36314b3a; exit=0; EXPECT=matched; output-sha256=7b5595d86dbca01277ebd597bb0f8a603bfffa7f73a94acae7aae5b678b27c49; output-bytes=49; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-meet; path=82de56a067b7/18 entries

- [x] G19: the PDF prints 16:9 pages and its page count equals the chapter count of the same snapshot; PDF text dates are Arabic words (no ISO date inside Arabic text); the PDF text passes the same privacy scan (zero hits)
  CHECK: "${OUJA_PY:-python3}" owner_meet/tools_layout_audit.py --pdf --fixture tests/fixtures/owner_meet/snapshot_full.json
  EXPECT: /^PDF_OK pages=(\d+) chapters=\1 ratio=1\.78 iso_dates=0 privacy=0$/m
  EVIDENCE: automatic-evidence=v1; definition-sha256=f47570bf9c4b64c0c210572d63f2b0a2802166794636152877d5f6833c577330; exit=0; EXPECT=matched; output-sha256=8dfd8858532c378909949f956b257da34abafe450c818d370e4ba1a5d2b33b55; output-bytes=61; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-meet; path=82de56a067b7/18 entries

- [x] G20: S6 — impeccable critique → audit → polish → harden pass done on the tab, presentation, presenter window, owner phone page and PDF; findings and fixes recorded in the plan's S6 log
  EVIDENCE: S6 log in docs/superpowers/plans/2026-10-06-owner-meet.md (2026-10-06): impeccable detector clean on stage/notes/owner page/3 JS files after the shadow fix; WCAG contrast measured for every pair (three raised to ≥ 5.2); keyboard, 44 px targets, reduced-motion, motion rules checked; harden list recorded.

- [x] G21: the waterfall starts at «صافي الحجوزات» — no guest-paid / VAT / Airbnb-fee rows and no reader of those Hostaway fields anywhere in owner_meet/ (Faisal 2026-10-06); test group A equals the plan PDF's 21 listings exactly and the `test` action stays silent until the list is confirmed
  CHECK: python3 -m unittest tests.test_owner_meet_structure.WaterfallScope tests.test_owner_meet_engine.PromoSplit 2>&1 | grep -E "^(OK|FAILED)" | tail -1
  EXPECT: /^OK/m
  EVIDENCE: automatic-evidence=v1; definition-sha256=11b0764c90c931cae37efaec9b68fb2c9a0c091f5272a3b25162fe8a4266bf8c; exit=0; EXPECT=matched; output-sha256=a12b7cb43c9d9134b5bb1b35e9096b66775d9e92e7611d1cc92b02edd6782a87; output-bytes=3; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-meet; path=82de56a067b7/18 entries

- [ ] G22: S1 reviewed by Faisal — the snapshot's owner net for one real owner/unit and period shown next to the same months in «الملاك» / the owner portal, matching
  EVIDENCE: pending

- [x] G23: S2 reviewed by Faisal — screenshots of chapters 1–6 on a real unit, desktop (1280×720) and phone (390 px), presenter window synced; nothing sent
  EVIDENCE: Faisal reviewed the S2 screenshots (chapters 1–6, multi-unit cover, notes window desktop + phone, tab) on 2026-10-06: «كويسه الصور» — one change asked (blue → Diriyah brown), applied in S3.

- [ ] G24: S3 reviewed by Faisal — chapters 7–10 screenshots on a real unit with tickets, a claim and reviews
  EVIDENCE: pending

- [ ] G25: S4 reviewed by Faisal — the real Airbnb report imported, mapping confirmed, chapters 11–12 screenshots
  EVIDENCE: pending

- [ ] G26: S5 reviewed by Faisal — a meeting recorded, sent, the owner link opened on his phone, the PDF downloaded, the WhatsApp message opened by his tap only, chapter 0 shown on a follow-up meeting
  EVIDENCE: pending

- [ ] G27: P9 live performance — one unit × 12 months snapshot measured warm (< 20 s) and cold (< 90 s) on Railway, presentation open < 1 s; numbers recorded
  EVIDENCE: pending

- [x] G30: S1 pure rules — percentile with half ties, round-to-10 halves up, labels never speak a number below 60 (top capped at 90), quartiles, bands carry no count, the unit is never its own peer, <6 peers → portfolio («شققنا»), too few → no band, fair-share index, 0/empty review scores ignored and 4.75 exact, period presets (quarter = 3 complete months, since-last starts the next day, custom clipped), waterfall reconcile / unreconciled / adjustment rows, per-100 sums to 100, degraded or red blocks send, rules file override + broken-edit fallback
  CHECK: python3 -m unittest tests.test_owner_meet_engine 2>&1 | grep -E "^(OK|FAILED)" | tail -1
  EXPECT: /^OK/m
  EVIDENCE: automatic-evidence=v1; definition-sha256=17f8e3daeb0ebc78eaf7a90cd6993ed2cbc34c9496372588b6291428a1d233c8; exit=0; EXPECT=matched; output-sha256=a12b7cb43c9d9134b5bb1b35e9096b66775d9e92e7611d1cc92b02edd6782a87; output-bytes=3; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-meet; path=82de56a067b7/18 entries

- [x] G31: owner-link routes (S5) — /m/{token} and /m/{token}.pdf live outside /api/meet/ and use HOST.web_thread; a wrong or revoked token returns the same status and body as a generic 404; 30/IP/min then 429; /api/meet/{id}/wa is login-gated and logs wa_opened; «إرسال» refuses while degraded or a red readiness line is open
  CHECK: python3 -m unittest tests.test_owner_meet_links 2>&1 | grep -E "^(OK|FAILED)" | tail -1
  EXPECT: /^OK/m
  EVIDENCE: automatic-evidence=v1; definition-sha256=44d188fef6b586d36b400d6e62b08c284aea4b98c00f6003e740752dadf036a9; exit=0; EXPECT=matched; output-sha256=a12b7cb43c9d9134b5bb1b35e9096b66775d9e92e7611d1cc92b02edd6782a87; output-bytes=3; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-meet; path=82de56a067b7/18 entries

- [ ] G28: nothing pushed to GitHub without Faisal's explicit word for that push; every push is from main-based work and verified live through an /api/ route
  EVIDENCE: pending

- [x] G29: S0 — spec, plan and this ledger approved by Faisal before the first code edit
  EVIDENCE: Faisal in chat 2026-10-06, after the S0 report: «موافق على الثلاث، مع تعديل على الثانية … بعدها ابدأ S1» (group A computed, not empty; tab admin-only; waterfall from صافي الحجوزات with no live Hostaway look). Group A then confirmed: «اتاكد ابدا اس ٢».
