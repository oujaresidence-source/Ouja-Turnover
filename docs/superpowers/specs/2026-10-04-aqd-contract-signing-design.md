# «العقود» — survey → contract → e-sign link → countersign (design)

Date: 2026-10-04 · Package: `aqd/` · Tab id: `aqd` · Owner-approved super-prompt (plan pre-approved, push approved).

## Problem
The account manager re-types the operating contract (template v2.1) by hand for every owner,
then chases a wet signature. Errors in the owner block (gender grammar, ID type, VAT line) and
the units table reach the client. Nothing records who signed what, when, from where.

## Outcome
1. Employee answers a 6-step survey (mostly choices) in the dashboard tab «العقود».
2. The answers fill the FROZEN legal text of v2.1 — only the 22 `{{placeholders}}` change.
3. «إنشاء رابط التوقيع» freezes the document (sha256), mints a token link (14 days).
4. The client opens `/sign/{token}` on a phone, passes a last-4 identity check, reads, types
   their name, draws a signature, consents, signs, downloads a PDF.
5. Ouja is notified (tab badge, dashboard toast, Discord «العقود»).
6. An admin countersigns → `final.pdf` sealed; the same link now serves the final copy.

## Precedent
DocuSign / Adobe Sign: a link per signer, an access check before the document shows, an
immutable document hash, drawn signature + typed name + consent, and a "Certificate of
Completion" appended to the PDF. Rebuilt on Ouja's stack, no third-party e-sign.

## Architecture (copies `onboarding/` + `permits/`)
| module | role |
|---|---|
| `host.py` | DI bridge; bot.py wires caps (incl. `web_thread`, `notify`, `public_base`). |
| `config.py` | `AQD_*` env + `aqd_settings` defaults, read at call time. |
| `catalogue.py` | THE survey: steps, fields, options, validators, Arabic labels. Server re-validates with it. |
| `engine.py` | PURE: validate, context, single-pass render, hash, state machine, evidence page, name similarity. |
| `db.py` | `aqd_contracts`, `aqd_events`, `aqd_settings` in brain.db via `brain.db.connect`. |
| `files.py` | `$STATE_DIR/aqd/<id>/` artifacts; signature PNG checks (magic, size, ink pixels). |
| `pdf.py` | HTML→PDF on the shared Chromium (`ouja_render._pw_pool` + `_pw_print`); degrades to HTML. |
| `notify.py` | Arabic texts → `HOST.notify`; once-only latch `notified_signed_at`. |
| `routes.py` | `/api/aqd/*` (login + role), `/api/aqd-t/*` (public token), `/sign/{token}`, static JS. |
| `sign_page.py` | Public HTML shell, zero backslashes, no data. |
| `static/aqd_tab.js`, `static/sign.js` | Real JS files (no Python-string backslash trap), `node --check`ed. |

## Key decisions
- **Frozen document with three overlay slots.** `frozen.html` is the full render with the
  version banner and both signature blocks left as HTML comment markers
  (`<!--aqd:version_banner-->`, `<!--aqd:sig_owner-->`, `<!--aqd:sig_operator-->`).
  `doc_sha256` hashes those bytes. Display / signed / final fill only the slots. Reason: a
  contract sent while the template is unapproved must not carry the «غير معتمد» watermark
  forever once the owner approves; and signatures are by definition added after freezing.
  User values are HTML-escaped, so a value can never forge a marker.
- **View key.** A correct last-4 mints a 30-minute random `view_key` returned to that browser
  only. The contract body, the PDF download and the sign call all require it. The token alone
  never reveals the body (which carries the full ID number).
- **No oracle.** Wrong token and wrong digits return the identical `{ok:false,error}` shape.
  5 wrong tries lock the contract for 60 minutes.
- **Signer = the person who types the last-4.** Individual self → owner ID; agent → agent ID;
  company → CR. The typed name is compared with that signer's name (≥0.6 after Arabic
  normalization).
- **PDPL.** Full ID numbers live only in `$STATE_DIR/aqd/<id>/` files. DB `answers_json` holds
  `••••••1234`. Discord and logs never carry an ID or a phone.
- **Signing is never blocked by PDF.** PDF failure → HTML fallback served; the state change
  and the notification still happen.
- **Template approval switch** (`template_approved`) ships OFF: links work read-only, signing
  refused, until an admin types «اعتماد» in settings.

## State machine
`draft → sent → opened → verified → signed_owner → completed`;
`draft|sent|opened|verified → void` (admin or creator, reason required);
`sent|opened|verified → expired` when now > expires_at (persisted on next touch);
`expired → sent` by «إعادة إرسال» (new token, same frozen doc).
`signed_owner` and `completed` can never be voided from the web; `completed` is final.

## Error contract
401 not logged in · 403 wrong role · 200 `{ok:false,error:<Arabic>}` refusal · 200 `{ok:true}`.
Public handlers never show a stack trace.

## Testing
TDD: `tests/test_aqd_engine.py` (catalogue rules, grammar, rows, render safety, hash, state
machine), `tests/test_aqd_routes.py` (roles, identity gate, lockout, no-oracle, sign refusals,
once-only notify, countersign), `tests/test_aqd_dashboard.py` (esprima, node --check, NAV,
permission maps, no to_thread). Synthetic end-to-end with PyMuPDF on the final PDF.
