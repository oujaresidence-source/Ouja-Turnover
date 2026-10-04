# Gates: «العقود» contract signing (aqd/)

OWNS: aqd/**, tests/test_aqd_*.py, bot.py (AQD glue only), CLAUDE.md, docs/superpowers/specs/2026-10-04-aqd-contract-signing-design.md

Scope: survey → filled v2.1 contract → token e-sign link → client signature → admin countersign → sealed PDF + notifications, shipped with the template UNAPPROVED (signing refused until an admin types «اعتماد»).

Run from the repo root: node <unlazy>/scripts/gate-check.mjs --cwd . aqd/GATES.md

- [x] G1: bot.py and every aqd module compile with SyntaxWarning as error
  CHECK: rm -rf __pycache__ aqd/__pycache__ && python3 -W error::SyntaxWarning -m py_compile bot.py aqd/__init__.py aqd/host.py aqd/config.py aqd/catalogue.py aqd/engine.py aqd/db.py aqd/files.py aqd/pdf.py aqd/notify.py aqd/routes.py aqd/sign_page.py && echo OK_COMPILE
  EXPECT: /^OK_COMPILE$/m
  EVIDENCE: automatic-evidence=v1; definition-sha256=e7084130f5e7f198f2122e236046c0f4136b66650d010d9985ec7c9808dd1645; exit=0; EXPECT=matched; output-sha256=54c4da2cec9fcd400f2f5ba44a954cdb7622e944e0642dfed41213c608092359; output-bytes=11; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-aqd; path=82de56a067b7/18 entries

- [x] G2: the three aqd test modules pass (on local Python 3.9 the one real-PDF test is skipped by design — G9 runs it on 3.13)
  CHECK: python3 -m unittest tests.test_aqd_engine tests.test_aqd_routes tests.test_aqd_dashboard 2>&1 | grep -E '^(Ran [0-9]+ tests|OK.*|FAILED.*)$'
  EXPECT: /^OK( \(skipped=1\))?$/m
  EVIDENCE: automatic-evidence=v1; definition-sha256=b186c4a2d604087088e2f7854260aa622f760e6e7e4478f8ac3e5c4dc0a69750; exit=0; EXPECT=matched; output-sha256=faa488b7581ae7bfc00cd12d751f871753558c933945bfa643ce25de502127c3; output-bytes=15; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-aqd; path=82de56a067b7/18 entries

- [x] G3: full suite — no NEW failures vs the baseline recorded on untouched origin/main (aqd/.baseline.txt)
  CHECK: python3 -c "import re,subprocess,sys;I=re.compile(r'^(?:FAIL|ERROR): (\S+ \(\S+\))',re.M);k=set(I.findall(open('aqd/.baseline.txt',encoding='utf-8').read()));o=subprocess.run([sys.executable,'-m','unittest','discover','-s','tests','-p','test_*.py'],capture_output=True,text=True);t=o.stdout+o.stderr;r=re.search(r'^Ran (\d+) tests',t,re.M);n=sorted(set(I.findall(t))-k);print('NEW_FAILURES',n) if (n or not r) else print('NO_NEW_FAILURES ran=%s' % r.group(1))"
  EXPECT: /^NO_NEW_FAILURES ran=\d+$/m
  EVIDENCE: automatic-evidence=v1; definition-sha256=33658c555111712a7cf50c86623463628ccbeaad75f8ba85523ea667b50b3972; exit=0; EXPECT=matched; output-sha256=78ed870955e4647b0de6676e26910c003ec34f9414167eac3f209a346519b518; output-bytes=25; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-aqd; path=82de56a067b7/18 entries

- [x] G4: both tab scripts parse under node
  CHECK: node --check aqd/static/aqd_tab.js && node --check aqd/static/sign.js && echo JS_OK
  EXPECT: /^JS_OK$/m
  EVIDENCE: automatic-evidence=v1; definition-sha256=1727f7fab9d3f6e532537f130b50f271ed1dd7bbefa5299cfc88b7f818d60b3c; exit=0; EXPECT=matched; output-sha256=cb5bbc09ee6cfa19f42a617de658151521bb40c1007e252da3f72c2bf68e47f5; output-bytes=6; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-aqd; path=82de56a067b7/18 entries

- [x] G5: every <script> of the served DASHBOARD_HTML parses (esprima)
  CHECK: python3 -c "import bot,esprima,re;[esprima.parseScript(j) for j in re.findall(r'<script>(.*?)</script>',bot.DASHBOARD_HTML,re.S)];print('ESPRIMA_OK')" 2>/dev/null
  EXPECT: /^ESPRIMA_OK$/m
  EVIDENCE: automatic-evidence=v1; definition-sha256=1900ba5c9e587db90230f6c98b1c0f505a6381554965c8e3b1617687cde83eaa; exit=0; EXPECT=matched; output-sha256=3226b625374b13554b389ad48b05e1d30aca55c9a1e25228ac7ed5a4783b7256; output-bytes=956; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-aqd; path=82de56a067b7/18 entries

- [x] G6: no asyncio.to_thread anywhere in aqd/
  CHECK: test -f aqd/routes.py && (grep -rn "to_thread" aqd/ --include=*.py --include=*.js || echo NO_TO_THREAD)
  EXPECT: /^NO_TO_THREAD$/m
  EVIDENCE: automatic-evidence=v1; definition-sha256=17e6205bc1da54b5ff704976c3903c98957c2c4cba20c4f7ddae2ceeab4c5c39; exit=0; EXPECT=matched; output-sha256=ef503e46eea4c1633f8ca37cc75944ac921024003675dd9f670008e3c580dc1c; output-bytes=13; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-aqd; path=82de56a067b7/18 entries

- [x] G7: no national-ID-shaped number leaves through git
  CHECK: python3 permits/tools_privacy_scan.py
  EXPECT: /PRIVACY_OK/
  EVIDENCE: automatic-evidence=v1; definition-sha256=60432aa470f609ea7ae16934eb797508fafd05d73e4faef4abe96d07c11f6d97; exit=0; EXPECT=matched; output-sha256=3ec1d0a9f3f2b250e999401eab03b2a83a1be03e8b5236d30b4e8161250e6f11; output-bytes=80; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-aqd; path=82de56a067b7/18 entries

- [x] G8: zero backslashes in aqd/sign_page.py and in the loadAqd stub inside bot.py
  CHECK: python3 -c "s=open('aqd/sign_page.py',encoding='utf-8').read();b=open('bot.py',encoding='utf-8').read();i=b.find('/* AQD-STUB-START */');j=b.find('/* AQD-STUB-END */');print('BACKSLASH_FREE' if (0<i<j and chr(92) not in s and chr(92) not in b[i:j]) else 'BACKSLASH_FOUND')"
  EXPECT: /^BACKSLASH_FREE$/m
  EVIDENCE: automatic-evidence=v1; definition-sha256=e311a3e52b819b53a59bd33eefe0315b99196ccf5d319084f81a352c102cc561; exit=0; EXPECT=matched; output-sha256=e776d3ae9441f6b9c7fa9a0b4a75b960fee2ab89a113717255ceadeba5b4d1e2; output-bytes=15; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-aqd; path=82de56a067b7/18 entries

- [x] G9: synthetic end-to-end in a temp STATE_DIR on Python 3.13 (Railway's runtime; the shared renderer needs ≥3.12) — create → send → open → verify → approve → sign → countersign → the REAL final PDF contains the ref, the client name and «سجل التوقيع الإلكتروني» (a skip prints "OK (skipped=1)" and fails this gate)
  CHECK: $AQD_PY313 -W ignore -m unittest tests.test_aqd_routes.TestEndToEnd 2>&1 | grep -E '^(Ran [0-9]+ tests|OK.*|FAILED.*)$'
  EXPECT: /^OK$/m
  EVIDENCE: automatic-evidence=v1; definition-sha256=31b79151f40d40c9089d3f42eaaa74496c42ad11795250ff24c6b8ce68b1508f; exit=0; EXPECT=matched; output-sha256=a12b7cb43c9d9134b5bb1b35e9096b66775d9e92e7611d1cc92b02edd6782a87; output-bytes=3; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-aqd; path=82de56a067b7/18 entries

- [x] G10: finance ERP SPA still parses (CLAUDE.md routine)
  CHECK: node --check finance/static/erp.js && echo ERP_JS_OK
  EXPECT: /^ERP_JS_OK$/m
  EVIDENCE: automatic-evidence=v1; definition-sha256=193c393f70835c2cbe43a9c3e92fa4a330c86d382e1573b55b52895f4612f376; exit=0; EXPECT=matched; output-sha256=2bf6e8618e32bcdb938a3f2cf65649521385a43fbab057b2689d2a9b10275107; output-bytes=10; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-aqd; path=82de56a067b7/18 entries

- [x] G11: pyflakes clean on aqd + its tests (ignoring "imported but unused")
  CHECK: python3 -m pyflakes aqd/ tests/test_aqd_engine.py tests/test_aqd_routes.py tests/test_aqd_dashboard.py | grep -v "imported but unused" | wc -l | tr -d ' ' | sed 's/^0$/FLAKES_CLEAN/'
  EXPECT: /^FLAKES_CLEAN$/m
  EVIDENCE: automatic-evidence=v1; definition-sha256=decc7fd1eec07b4cb5cbce99711e823f467350324eba20f115e6c24c1c0c9412; exit=0; EXPECT=matched; output-sha256=948963639f94dc5c4dfa63210ebf942cecf1ff8fc8308c49be432c6ac1029b71; output-bytes=13; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-aqd; path=82de56a067b7/18 entries

- [x] G12: impeccable audit + polish pass done on the tab and on /sign at 390px and 1280px (screenshots reviewed)
  EVIDENCE: 2026-10-04 — local test server (fake data) driven by Playwright at 390×844 and 1280×860: gate, wrong digits, unapproved read-only view, sign panel, done state, tab list, wizard steps 1/3/6, signed-contract drawer; zero page errors. Detector: 2 findings (width transition on the reading bar, an <img> without src) fixed, plus manual fixes (SVG state icons instead of glyphs, h1 on the sign page, muted text darkened for AA, themed ::selection/caret, status dots instead of glyphs, masked ID forced LTR). Re-run: detector [] and screenshots clean.

## Assumptions (decisions this prompt did not foresee — safest, reversible, closest to an existing pattern)

1. **Branch / worktree.** The primary checkout is parked on `feat/musaed-v2` and is shared with
   other sessions, so the work is built in the worktree `../ouja-wt-aqd` (branch `feat/aqd`
   from `origin/main`) and fast-forwarded onto `main` at push time. Local `main` was 169+
   commits behind `origin/main`; `origin/main` is the base.
2. **G3 = "no new failures".** The full suite was already red on untouched `origin/main`
   (date-dependent tests, see memory). G3 compares failing ids against `aqd/.baseline.txt`,
   recorded before any change (the baseline file is not committed).
3. **Overlay slots in the frozen document.** `version_banner`, `sig_owner`, `sig_operator` are
   frozen as HTML-comment markers and filled at display/sign time. Otherwise a contract sent
   before approval would carry «غير معتمد» forever, and signatures cannot be inside a document
   that is hashed before signing. User values are escaped, so they cannot forge a marker.
4. **View key.** The prompt says sign needs "verified in the last 30 min". A verified timestamp
   alone would let a second person with the link sign inside that window; the verify call
   therefore returns a random 30-minute `view_key` (two extra columns `view_key`,
   `view_key_until`) that the sign call, the contract body and the PDF download require.
5. **Who verifies / signs.** The person who signs passes the check: owner ID (self), agent ID
   (signer=agent), or CR (company). Typed-name similarity compares against that same person
   (owner / agent / company representative).
6. **Passport / GCC ID last-4 may contain letters**, so the four boxes accept letters when
   `id_type=other` (the API says which).
7. **CR numbers are masked like IDs in the DB** (old CRs start with 1 and look like a national
   ID to the privacy scan). VAT numbers (15 digits) are kept.
8. **The FAL licence default** is written by concatenation in `config.py` because it is ten digits
    starting with 2 — ID-shaped to the privacy scan — though it is a licence, not a person's ID.
9. **Countersign needs the operator signature AND stamp uploaded** in settings; otherwise it
   is refused with a clear Arabic reason (sealing a contract without them would be worse).
10. **Notify retry "tick".** There is no aqd loop; every `/api/aqd/list` call (the 60-second
    tab poll + badge poll) retries delivery for `signed_owner` rows whose
    `notified_signed_at` is still NULL.
11. **Discord channel placement.** `AQD_CHANNEL` text channel is created on first use under the
    «ضم الوحدات» category by reusing bot.py's `_onb_category`; the notify hook is thread-safe
    (`run_coroutine_threadsafe`, the `_ops_notify` lesson) because handlers call it from the
    web pool.
12. **Display fonts.** The frozen file embeds the three Thmanyah fonts as base64 (the PDF needs
    them offline). For the phone view and the dashboard preview the same `@font-face` block is
    swapped for `/guide/fonts/thmanyahsans-*.woff2` URLs to cut ~320 KB per load; the bytes
    that are hashed are never altered.
13. **AQD_ENABLED=0** removes `aqd` from the sidebar at boot and makes every aqd route answer
    "invalid / disabled"; routes stay registered so the switch needs only a restart.
14. **Expired contracts can be resent, not voided** — the state machine is kept exactly as
    specified.
15. **PDF engine.** `_pw_print` prints with zero margins, which Chromium overrides with the
    template's own `@page` margins (verified by rendering). If Playwright is not importable the
    stored artifact is the HTML and downloads serve HTML.
16. **Anonymous `/api/aqd/list` answers 403, not 401, on the live server**: bot.py's role middleware
    runs before the handler and refuses any page-scoped read without a user (same as `/api/onb/list`).
    The handler's own guard is 401 (tested). Either code proves the door exists and is locked.
17. **Contract date = the moment the link is created** (the freeze), not the draft's first save —
    that is when the document is actually issued. Previews show today's date.
18. **Unit table on a phone** scrolls sideways inside the contract frame (9 legal columns cannot fit
    360 px); the page itself never scrolls sideways.
