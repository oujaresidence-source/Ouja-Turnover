# Gates: «العقود» contract signing (aqd/)

OWNS: aqd/**, tests/test_aqd_*.py, bot.py (AQD glue only), CLAUDE.md, docs/superpowers/specs/2026-10-04-aqd-contract-signing-design.md

Scope: survey → filled v2.1 contract → token e-sign link → client signature → admin countersign → sealed PDF + notifications, shipped with the template UNAPPROVED (signing refused until an admin types «اعتماد»).

Run from the repo root: node <unlazy>/scripts/gate-check.mjs --cwd . aqd/GATES.md

- [x] G1: bot.py and every aqd module compile with SyntaxWarning as error
  CHECK: rm -rf __pycache__ aqd/__pycache__ && python3 -W error::SyntaxWarning -m py_compile bot.py aqd/__init__.py aqd/host.py aqd/config.py aqd/catalogue.py aqd/engine.py aqd/db.py aqd/files.py aqd/pdf.py aqd/notify.py aqd/routes.py aqd/sign_page.py && echo OK_COMPILE
  EXPECT: /^OK_COMPILE$/m
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-aqdb; path=985fd6ae610d/17 entries; EXPECT=matched; output-sha256=54c4da2cec9fcd400f2f5ba44a954cdb7622e944e0642dfed41213c608092359; output-bytes=11

- [x] G2: the three aqd test modules pass (on local Python 3.9 the real-PDF tests — 2 since Upgrade 3 — are skipped by design; G9 runs them on 3.13)
  CHECK: python3 -m unittest tests.test_aqd_engine tests.test_aqd_routes tests.test_aqd_dashboard 2>&1 | grep -E '^(Ran [0-9]+ tests|OK.*|FAILED.*)$'
  EXPECT: /^OK( \(skipped=[12]\))?$/m
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-aqdb; path=985fd6ae610d/17 entries; EXPECT=matched; output-sha256=55d9eedfe7a7d2017c4e7579a58b1d4de6a5262847ba277e3846fba4b0986791; output-bytes=15

- [x] G3: full suite — no NEW failures vs the baseline recorded on untouched origin/main (aqd/.baseline.txt)
  CHECK: python3 -c "import re,subprocess,sys;I=re.compile(r'^(?:FAIL|ERROR): (\S+ \(\S+\))',re.M);k=set(I.findall(open('aqd/.baseline.txt',encoding='utf-8').read()));o=subprocess.run([sys.executable,'-m','unittest','discover','-s','tests','-p','test_*.py'],capture_output=True,text=True);t=o.stdout+o.stderr;r=re.search(r'^Ran (\d+) tests',t,re.M);n=sorted(set(I.findall(t))-k);print('NEW_FAILURES',n) if (n or not r) else print('NO_NEW_FAILURES ran=%s' % r.group(1))"
  EXPECT: /^NO_NEW_FAILURES ran=\d+$/m
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-aqdb; path=985fd6ae610d/17 entries; EXPECT=matched; output-sha256=e4841137520613324f12397078a7b92f433417173512f0ea176d1863c4b063c0; output-bytes=25

- [x] G4: both tab scripts parse under node
  CHECK: node --check aqd/static/aqd_tab.js && node --check aqd/static/sign.js && echo JS_OK
  EXPECT: /^JS_OK$/m
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-aqdb; path=985fd6ae610d/17 entries; EXPECT=matched; output-sha256=cb5bbc09ee6cfa19f42a617de658151521bb40c1007e252da3f72c2bf68e47f5; output-bytes=6

- [x] G5: every <script> of the served DASHBOARD_HTML parses (esprima)
  CHECK: python3 -c "import bot,esprima,re;[esprima.parseScript(j) for j in re.findall(r'<script>(.*?)</script>',bot.DASHBOARD_HTML,re.S)];print('ESPRIMA_OK')" 2>/dev/null
  EXPECT: /^ESPRIMA_OK$/m
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-aqdb; path=985fd6ae610d/17 entries; EXPECT=matched; output-sha256=2228c06d2966f53d88ec79de61d3b7d09547468532a7f699a902447a2118747f; output-bytes=956

- [x] G6: no asyncio.to_thread anywhere in aqd/
  CHECK: test -f aqd/routes.py && (grep -rn "to_thread" aqd/ --include=*.py --include=*.js || echo NO_TO_THREAD)
  EXPECT: /^NO_TO_THREAD$/m
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-aqdb; path=985fd6ae610d/17 entries; EXPECT=matched; output-sha256=ef503e46eea4c1633f8ca37cc75944ac921024003675dd9f670008e3c580dc1c; output-bytes=13

- [x] G7: no national-ID-shaped number leaves through git
  CHECK: python3 permits/tools_privacy_scan.py
  EXPECT: /PRIVACY_OK/
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-aqdb; path=985fd6ae610d/17 entries; EXPECT=matched; output-sha256=685aeb50c3b01fe0b335fd740c6338515538c1b5b780e5fd143695e9f084defa; output-bytes=80

- [x] G8: zero backslashes in aqd/sign_page.py and in the loadAqd stub inside bot.py
  CHECK: python3 -c "s=open('aqd/sign_page.py',encoding='utf-8').read();b=open('bot.py',encoding='utf-8').read();i=b.find('/* AQD-STUB-START */');j=b.find('/* AQD-STUB-END */');print('BACKSLASH_FREE' if (0<i<j and chr(92) not in s and chr(92) not in b[i:j]) else 'BACKSLASH_FOUND')"
  EXPECT: /^BACKSLASH_FREE$/m
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-aqdb; path=985fd6ae610d/17 entries; EXPECT=matched; output-sha256=e776d3ae9441f6b9c7fa9a0b4a75b960fee2ab89a113717255ceadeba5b4d1e2; output-bytes=15

- [x] G9: synthetic end-to-end in a temp STATE_DIR on Python 3.13 (Railway's runtime; the shared renderer needs ≥3.12) — create → send → open → verify → approve → sign → countersign → the REAL final PDF contains the ref, the client name and «سجل التوقيع الإلكتروني» (a skip prints "OK (skipped=1)" and fails this gate)
  CHECK: $AQD_PY313 -W ignore -m unittest tests.test_aqd_routes.TestEndToEnd 2>&1 | grep -E '^(Ran [0-9]+ tests|OK.*|FAILED.*)$'
  EXPECT: /^OK$/m
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-aqdb; path=985fd6ae610d/17 entries; EXPECT=matched; output-sha256=a12b7cb43c9d9134b5bb1b35e9096b66775d9e92e7611d1cc92b02edd6782a87; output-bytes=3

- [x] G10: finance ERP SPA still parses (CLAUDE.md routine)
  CHECK: node --check finance/static/erp.js && echo ERP_JS_OK
  EXPECT: /^ERP_JS_OK$/m
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-aqdb; path=985fd6ae610d/17 entries; EXPECT=matched; output-sha256=2bf6e8618e32bcdb938a3f2cf65649521385a43fbab057b2689d2a9b10275107; output-bytes=10

- [x] G11: pyflakes clean on aqd + its tests (ignoring "imported but unused")
  CHECK: python3 -m pyflakes aqd/ tests/test_aqd_engine.py tests/test_aqd_routes.py tests/test_aqd_dashboard.py | grep -v "imported but unused" | wc -l | tr -d ' ' | sed 's/^0$/FLAKES_CLEAN/'
  EXPECT: /^FLAKES_CLEAN$/m
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-aqdb; path=985fd6ae610d/17 entries; EXPECT=matched; output-sha256=948963639f94dc5c4dfa63210ebf942cecf1ff8fc8308c49be432c6ac1029b71; output-bytes=13

- [x] G12: impeccable audit + polish pass done on the tab and on /sign at 390px and 1280px (screenshots reviewed)
  EVIDENCE: 2026-10-04 — local test server (fake data) driven by Playwright at 390×844 and 1280×860: gate, wrong digits, unapproved read-only view, sign panel, done state, tab list, wizard steps 1/3/6, signed-contract drawer; zero page errors. Detector: 2 findings (width transition on the reading bar, an <img> without src) fixed, plus manual fixes (SVG state icons instead of glyphs, h1 on the sign page, muted text darkened for AA, themed ::selection/caret, status dots instead of glyphs, masked ID forced LTR). Re-run: detector [] and screenshots clean.

## Upgrade 2 — the six owner rules (R1–R6)

- [x] G13: engine + routes tests pass (the one real-PDF test may skip on local 3.9 — G9 runs it)
  CHECK: python3 -m unittest tests.test_aqd_engine tests.test_aqd_routes 2>&1 | grep -E '^(OK.*|FAILED.*)$'
  EXPECT: /^OK( \(skipped=\d\))?$/m
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-aqdb; path=985fd6ae610d/17 entries; EXPECT=matched; output-sha256=55d9eedfe7a7d2017c4e7579a58b1d4de6a5262847ba277e3846fba4b0986791; output-bytes=15

- [x] G14: the company / Ouja-account / 4-unit / operator / 15-try rules hold at the HTTP boundary (routes.core_* through the handlers, temp STATE_DIR)
  CHECK: python3 -m unittest tests.test_aqd_routes.TestUpgradeRules 2>&1 | grep -qE '^OK$' && echo ROUTING_OK
  EXPECT: /^ROUTING_OK$/m
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-aqdb; path=985fd6ae610d/17 entries; EXPECT=matched; output-sha256=29f8739109069bc4640fe317f74f31c2cb8361f99b4bbad769c8c1e4dbc2d42e; output-bytes=11

- [x] G15: bot.py is unchanged by this task
  CHECK: git diff --quiet HEAD -- bot.py && echo BOT_UNTOUCHED
  EXPECT: /^BOT_UNTOUCHED$/m
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-aqdb; path=985fd6ae610d/17 entries; EXPECT=matched; output-sha256=e25c4e2febed6c9a8479392cf9e8dc0fdd833961246dcc1eed26a4e954fe7bd7; output-bytes=14

- [x] G16: both tab scripts still parse under node
  CHECK: node --check aqd/static/aqd_tab.js && node --check aqd/static/sign.js && echo JS_OK
  EXPECT: /^JS_OK$/m
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-aqdb; path=985fd6ae610d/17 entries; EXPECT=matched; output-sha256=cb5bbc09ee6cfa19f42a617de658151521bb40c1007e252da3f72c2bf68e47f5; output-bytes=6

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

### Upgrade 2 (R1–R6) — assumptions
19. **Sign-time route check = "still routes", not "same name".** The prompt asks for
    `template_for(answers) == c.template_name`. Taken literally, switching `AQD_TEMPLATE` to v2.2
    would make every sent v2.1 contract unsignable — contradicting the documented swap procedure
    (sent contracts keep their frozen v2.1). The check refuses when the answers no longer route to
    ANY approved template (company / Ouja account), which is the defect R2 targets.
20. **Old contracts without `account_model`:** routed as "owner" only when VAT-registered; otherwise
    they have no route → draft: a normal "required" error; sent: flagged «needs_reissue» at boot and
    unsignable. Live had no client-signed contracts (shipped unapproved the same day).
21. **The VAT-yes line is a `note` field** (`account_model_note`, type "note") so the tab renders it
    from the catalogue like every other field; validate() skips note fields.
22. **Rule texts live in `catalogue.py`** (one source for server refusals, tab cards and tests);
    `engine.template_for` reads them. `send_blockers` imports engine locally (engine imports
    catalogue at load).
23. **`aqd/notify.py` is a 12th file** — the attempts-cap Discord line sits with the other notification
    texts. The commit has 12 files, not 11.
24. **Settings dates:** the date inputs send ISO; the server stores `dd/mm/yyyyم` (the text the contract
    prints). Typed text that is not ISO is stored as typed.
25. **15-try cap:** counted on wrong digits only (not on wrong tokens, which never reach a contract);
    on the 15th the phone still gets the generic wrong-digits answer, then the ordinary expired card.
26. **Tests changed** (as allowed): engine fixture `individual()` gained `account_model="owner"` (R1
    makes it required); `test_more_than_three_in_one_property_needs_the_tick_and_warns` became
    `…_is_a_hard_block` (+ old-draft test); `test_company_verifies_with_cr_and_rep_name` became
    `test_company_draft_saves_but_no_link_is_created`; the routes harness `boot()` now fills the
    operator data (every send needs it; `clear_operator()` exercises the refusal). The 15-try test
    resets the in-process 10/min rate limit between lock windows (they are an hour apart in life).
27. **Pre-existing bug fixed during the required audit:** typing in a wizard field and then pressing
    «التالي» lost the first click (the field's change event re-rendered the footer between mousedown
    and mouseup). `syncNext()` now updates the existing button in place. Found by the 390/1280 audit
    run; it blocked the changed steps.

## Upgrade 3 — Model (B) «حساب عوجا» + template v2.2 + per-template approval (2026-10-12)

- [x] G17: v2.2 has the 22 shared placeholders; Model (B) has exactly those + payout_period; both carry their defining text
  CHECK: python3 -c "import re;f=lambda n:open('aqd/templates/'+n+'.html',encoding='utf-8').read();a=f('operating_v2_2');b=f('operating_ouja_v2_2');pa=set(re.findall(r'\{\{(\w+)\}\}',a));pb=set(re.findall(r'\{\{(\w+)\}\}',b));print('TPL_OK' if len(pa)==22 and pb==pa|{'payout_period'} and 'حساب المشغّل:' in b and 'أيام الحجب:' in a else 'TPL_BAD')"
  EXPECT: /^TPL_OK$/m
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-aqdb; path=985fd6ae610d/17 entries; EXPECT=matched; output-sha256=588d1789e3a18e1b2bd1c1bb0859b0647ce5ea7f328fac4e57eccf6d30ac1bac; output-bytes=7

- [x] G18: Model B routing and refusals hold at the HTTP boundary (routes.core_* through the handlers, temp STATE_DIR)
  CHECK: python3 -m unittest tests.test_aqd_routes.TestModelB 2>&1 | grep -qE '^OK$' && echo MODEL_B_OK
  EXPECT: /^MODEL_B_OK$/m
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-aqdb; path=985fd6ae610d/17 entries; EXPECT=matched; output-sha256=3bd1c76393db64938d4f305f3a125627b64a71213b35eb474c84ac542802a291; output-bytes=11

- [x] G19: bot.py is unchanged by this task
  CHECK: git diff --quiet HEAD -- bot.py && echo BOT_UNTOUCHED
  EXPECT: /^BOT_UNTOUCHED$/m
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/Users/faisalouja/ouja-wt-aqdb; path=985fd6ae610d/17 entries; EXPECT=matched; output-sha256=e25c4e2febed6c9a8479392cf9e8dc0fdd833961246dcc1eed26a4e954fe7bd7; output-bytes=14

- [x] G20: impeccable audit on the changed wizard step + settings drawer + contract drawer at 390 px and 1280 px
  EVIDENCE: 2026-10-12 — local harness (real DASHBOARD_HTML + real aqd routes, temp brain.db, fake data) driven by Playwright at 390×844 and 1280×860: list banner names each unapproved template; VAT step with Model B shows the two questions, the IBAN box is LTR, a wrong check digit shows «رقم الآيبان غير صحيح — راجعه حرف حرف» and «التالي» stays locked; settings shows one card per template; typing «اعتماد» in the Model B card approved ONLY Model B (2.2 and 2.1 stayed unapproved); contract drawer shows «نموذج العقد» + the Model B go-live task. Zero page errors, no horizontal overflow at either width. One fix from the audit: the 2.1 card now says it is only for contracts already sent on it.

### Upgrade 3 — assumptions
28. **Templates built by the prompt's script** (`/tmp`-style scratch, deleted) from `operating_v2_1.html`; both
    SHA-256 matched on the first run (`TEMPLATES_OK`). `operating_v2_1.html` is kept for the 2.1 contracts already out.
29. **Sign-time check tightened from "still routes" (assumption 19) to "routes to the same account MODEL"**
    (`engine.template_fits`). Once Model B routes, "still routes" would let an Ouja-account contract
    frozen on 2.1 — whose text says the units run on the OWNER's account — sign after 2.1 is approved.
    Same model ⇒ fine (2.1 → 2.2 owner contracts keep signing); different model ⇒ «needs_reissue».
30. **The two Model B questions also require `client_kind=individual`** in `show_if`. The prompt gave
    `{"account_model": ["ouja"]}` only; a company on «حساب عوجا» was then asked for an IBAN, and that
    «مطلوب» error masked the company refusal at send. A company can never use Model B, so it never sees them.
31. **`build_context` returns 23 keys** (`engine.KEYS` = the 22 shared ones, `engine.EXTRA_KEYS` =
    `payout_period`). The prompt asks to always add `payout_period`, and the old test pinned the
    context to exactly KEYS — updated to `KEYS + EXTRA_KEYS`. The v2.1/v2.2 placeholder tests still
    assert exactly the 22.
32. **Tests changed** (beyond the «حساب عوجا يحتاج نموذج…» ones the prompt allows): `test_template_for`
    now expects `operating_v2_2` (the prompt moves the owner route to 2.2);
    `test_send_refused_for_an_individual_on_the_ouja_account` → `…_for_a_company_on_the_ouja_account`;
    `test_unrouted_contracts_cannot_be_sent` checks Model B now has no blockers;
    `test_airbnb_account_question_only_for_the_owner_account` uses the full Model B fixture (IBAN now
    required); the routes `approve()` helper and two approval tests pass `template` (now required).
33. **"core_get never contains the full IBAN"** is tested on the normal read (`edit` off). The edit
    read (`?edit=1`, the employee resuming a draft) returns `draft_answers.json` exactly as before —
    the same place the full ID already lives for that purpose.
34. **Unknown template name** = anything that is not a shipped `aqd/templates/operating_*.html` file
    (`config.known_templates()`), so «2.1» stays approvable for old contracts. Missing name → «حدّد أي نموذج تعتمد».
35. **List banner** lists only the templates NEW contracts would use (`templates_pending`); the legacy
    2.1 card appears in Settings only while a contract frozen on it still waits for a signature
    (sent/opened/verified/expired), marked «للعقود اللي انرسلت عليه قبل النموذج الجديد فقط».
36. **Draft rows now refresh `template_name`/`template_version` on every save** (they were set only on
    create), so the drawer's «نموذج العقد» is right after switching account model; send still sets them.
37. **Real-PDF needle:** PyMuPDF text extraction drops the «غّ» ligature glyph, so «المشغّل» extracts as
    «المشّل». Page 1 of the Model B `final.pdf` was rasterised and reads «حساب المشغّل» correctly; the
    test accepts either form and also checks «صافي المالك», «بصفته وكيل» and «سجل التوقيع الإلكتروني».
38. **`AQD_TEMPLATE` on Railway:** if it was ever set to `operating_v2_1`, model (أ) keeps sending on 2.1
    (it overrides only that route). Settings then shows the 2.1 card as active — visible, not silent.
39. **G3 baseline** for this run = untouched `origin/main` 71fceaf + the two new template files: 3
    pre-existing date-dependent failures (`test_ops_capture.TestBackfill` ×2, `test_train_export`).
40. **G2's pattern now allows `skipped=1|2`**: Upgrade 3 adds a second real-PDF test (Model B), and both
    skip on local 3.9 by design. G9 runs both on 3.13 and must print a bare `OK` (any skip fails it).

### Owner rulings 2026-10-13 (follow-up commit)
41. **Model (B) is version 2.2**, not 1.0: the file is renamed `operating_ouja_v2_2.html` (content
    byte-identical — still the SHA-256 the build script checked). Safe: live had 2 drafts and 0 sent
    contracts, and no approval had been stored for the 1.0 name.
42. **No وكالة in the contract and no operator gate beyond the rep's name**: «الممثل وصفته» prints the
    name from Settings only (`engine.op_rep_full`); `OPERATOR_FIELDS` = rep name only, so «اعتماد» and
    «إنشاء رابط التوقيع» no longer wait for the وكالة number/date or the CR expiry (prints «—» if empty).
    The client's OWN agent row (owner signing through a وكيل) is unchanged.
