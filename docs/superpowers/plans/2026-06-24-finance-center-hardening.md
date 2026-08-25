# Finance Center Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Ouja Finance ERP "المركز المالي" Approval Center correct and impossible to regress silently — fix the two confirmed bugs at their root, fix every same-class sibling, and add automated guardrails (JS syntax gate + contract test + V4 lifecycle tests) so the next contract drift fails a test instead of reaching the owner.

**Architecture:** Two confirmed bugs are instances of a *contract-drift* failure mode and a *terminal-state-affordance + optimistic-UI* failure mode. We pick ONE canonical data shape for the expense tab counts and make backend + frontend agree; we make `_exp4_approve` the single honest source of truth that refuses no-op approvals with a reason; we make the bulk affordance tab-aware and the frontend reconcile against the server's real result while keeping chip counts live. Every fix is written test-first.

**Tech Stack:** Python 3.9 (`bot.py` V4 state machine + aiohttp handlers), hand-written ES5 SPA (`finance/static/erp.js`, no build step), `unittest`/`pytest`, `node --check` + `esprima` for JS gating.

---

## Root cause — proven, not assumed (systematic-debugging Phase 1–3)

Reproduced with `_finance_repro.py` (Python, drives the live `bot.py` state machine) and Node (real JS coercion). Evidence:

- **BUG 1 (chips show `[object Object]`):** `bot._exp4_overview_data()['tabs']` returns `{k: {"count": N, "sar": X}}` (an object per tab). `erp.js` `renderExp()` renders the badge as `' <b>' + tabs[k] + '</b>'`. In JS, `'' + {count,sar}` === `"[object Object]"` (Node-confirmed). In RTL the badge sits left of the label → owner sees `[object Object] متحققة`. **Every other counter in the ERP is a scalar** (`g.count`, `d.counts.all`, `patchCounters`), so this object shape is the lone outlier and the renderer was never updated to read `.count`. No other `.tabs`/coercion site exists (audit CLASS 4 found only this one).
- **BUG 2 (press اعتماد → row returns to متحققة):** three layers, all reproduced:
  1. **Affordance:** `expRowHtml()` renders an `x-sel` checkbox on *every* tab (including `verified`, which has no per-row action), and `updateExpBulk()` offers bulk **Approve** on every tab except `approved` — so `verified`/`exported` get an Approve button the state machine can't honor.
  2. **Backend dishonesty:** `_exp4_approve()` flips `approval_status="approved"` and returns `(True,"approved")` for an already-verified/exported expense, but `_exp4_tab()` gives export-status precedence (`hostaway_verified → "verified"`), so the item never leaves its tab. A no-op reported as success. *(Repro: `_exp4_approve(verified_exp)` → `(True,"approved")` yet `_exp4_tab` stays `"verified"`.)*
  3. **Optimistic UI:** the `x-bulk-approve` handler removes the rows from `r.approved` and toasts success without reconciling tab membership or refreshing counts — so a no-op looks done until reload.

## Audit table — same-class sweep across the whole Financial Center

Classes: **C1** route/contract drift · **C2** optimistic UI · **C3** terminal-state no-op · **C4** dead button/orphan handler · **C5** i18n parity. Automated analyzer (`_finance_audit.py`) + Node ground-truth.

| # | File · line | Class | Symptom | Fix | Test |
|---|---|---|---|---|---|
| 1 | `finance/static/erp.js:2724` | C1 | `' <b>' + tabs[k]` → `[object Object]` (tab value is `{count,sar}`) | Chip reads `tabs[k].count`; show `.sar` as quiet secondary | contract: chip expr reads `.count`; lifecycle: `tabs[k]` is `{count:int,sar:num}` |
| 2 | `bot.py:_exp4_approve:11561` | C3 | Approving verified/exported/split/failed/dup returns `(True,"approved")` but `_exp4_tab` keeps it put — silent no-op | Guard: refuse with bilingual reason unless approve actually lands it in `approved` | lifecycle: approve verified→blocked, tab unchanged |
| 3 | `finance/static/erp.js:2762` `updateExpBulk` | C3 | Bulk **Approve** offered on `verified`/`exported` (no valid action) | `expBulkAction(tab)` single source: approve only on pending/needs_action, export on approved, none on exported/verified | contract: bulk action map; manual UI |
| 4 | `finance/static/erp.js:2615` `expRowHtml` | C3 | Selection checkbox rendered on terminal tabs with no bulk action | Render `x-sel` only when `expBulkAction(expP.tab)` is truthy | manual UI: no checkbox on verified |
| 5 | `finance/static/erp.js:1614` `x-bulk-approve/export` | C2 | Optimistic removal from `r.approved` + success toast; counts never refreshed | Remove only server-returned ok ids; show blocked w/ reasons; patch chips from `r.tabs`; reload to empty-state when list drains | lifecycle proves `blocked` populated; manual UI |
| 6 | `finance/static/erp.js:1592` `x-confirm-reject` | C2 | Unconditional `expRemoveRow` ignores response — rejecting on `needs_action` removes a row that stays in `needs_action` | Reconcile via returned `view.tab`: remove only if it left the current tab, else refresh in place | lifecycle: reject keeps failed item in needs_action |
| 7 | `bot.py` `_api_exp4_approve/_export/_recheck/_reject` | C2 | Responses omit refreshed tab counts → chips go stale after any action | Add `out["tabs"] = _exp4_tab_counts()` to all four | lifecycle: response includes `tabs`; contract |
| 8 | `bot.py:_exp4_overview_data:35900` | — (DRY) | Tab counting inlined; risks drift vs action responses | Extract `_exp4_tab_counts()`; both call it | lifecycle: counts == rows-per-tab |
| — | routes (`finance/__init__.py`) | C1 | — | **No drift found** — all 61 `/erp/api/*` paths the JS calls are registered | contract locks it |
| — | `data-act` tokens | C4 | — | **No dead buttons / orphans** — 3 "unhandled" were dynamic (`'confirm-'+kind`, `retryAct`, `cls+'-go'`); `confirm-reject`→`x-confirm-reject` in-place rewrite verified | contract locks it |
| — | i18n `T.ar`/`T.en` | C5 | — | **Perfect** — Node-eval: ar=615, en=615, 0 parity gaps, 0 absent across 531 literal `t()` keys | contract locks it |

**Net:** the disciplined parts are disciplined. Real work = items 1–8 (the two bugs + their direct C2/C3 siblings) + guardrails. New i18n keys added in this work must keep ar==en (contract test enforces).

## File structure

- **Modify `bot.py`** — `_exp4_approve` (honesty guards); NEW `_exp4_tab_counts`; `_exp4_overview_data` (reuse it); `_api_exp4_approve/_export/_recheck/_reject` (return `tabs`).
- **Modify `finance/static/erp.js`** — `renderExp` chip (BUG 1); NEW `expBulkAction`/`expApplyCounts`/`expBlockMsg`; `expRowHtml` (conditional checkbox); `updateExpBulk` (tab-aware); `x-bulk-*` handler (reconcile); `x-confirm-reject` (reconcile); single `x-approve`/`x-export`/`x-recheck` (patch counts); `T.ar`/`T.en` (5 block-reason keys, parity).
- **Modify `finance/static/erp.css`** — `.fchip .chip-sar` token; confirm press feedback + reduced-motion.
- **Create `tests/test_exp4_lifecycle.py`** — V4 state-machine matrix (no network).
- **Create `tests/test_erp_exp_contract.py`** — frontend↔backend contract + data-act + i18n parity.
- **Modify `CLAUDE.md`** — verification routine adds finance module; "Finance ERP traps" note.
- **Delete** scratch `_finance_repro.py`, `_finance_audit.py`, `_i18n_cov.js` (logic promoted into the real tests).

---

## Task 0: Baseline — confirm a green starting gate

**Files:** none (read-only)

- [ ] **Step 1: Run the current gate and record state**

Run:
```bash
rm -rf __pycache__
python3 -W error::SyntaxWarning -m py_compile bot.py
python3 -m pyflakes bot.py finance/*.py | grep -v "imported but unused" || true
node --check finance/static/erp.js
python3 -m pytest tests/ -q
```
Expected: compile clean; node check clean; existing tests pass. Record the pass count as the floor (no existing test may break).

---

## Task 1: BUG 1 — chip reads `.count` (contract drift fix)

**Files:**
- Test: `tests/test_erp_exp_contract.py` (created here, expanded in Task 6)
- Modify: `finance/static/erp.js:2719-2725`
- Modify: `finance/static/erp.css` (chip-sar)

- [ ] **Step 1: Write the failing contract test**

Create `tests/test_erp_exp_contract.py`:
```python
# -*- coding: utf-8 -*-
"""Frontend<->backend contract for the expense Approval Center.
Guards the EXACT drift classes that have reached the owner: the chip badge
must read .count (not stringify the {count,sar} object), and the served tab
shape must stay {count:int, sar:number}."""
import pathlib, re, unittest
import bot

JS = pathlib.Path("finance/static/erp.js").read_text("utf-8")


class ChipContract(unittest.TestCase):
    def test_backend_tabs_shape_is_count_sar(self):
        bot._expenses.clear()
        bot._expenses["c1"] = {"id": "c1", "amount": 10.0, "expense_date": "2026-05-01",
                               "apartment": "Ouja | X", "listing_id": 1, "category": "صيانة",
                               "approval_status": "pending_approval"}
        tabs = bot._exp4_overview_data(tab="pending")["tabs"]
        self.assertEqual(set(tabs), {"pending", "approved", "exported", "verified", "needs_action"})
        for k, v in tabs.items():
            self.assertIsInstance(v, dict, k)
            self.assertIsInstance(v["count"], int, k)
            self.assertIsInstance(v["sar"], (int, float), k)

    def test_chip_renderer_reads_count_not_object(self):
        # the exact broken token must be gone, and the chip must access .count
        self.assertNotIn("' <b>' + tabs[k] + '</b>'", JS)
        self.assertNotIn('+ tabs[k] +', JS.replace("tabs[k].count", ""))
        self.assertRegex(JS, r"tabs\[k\]\.count")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it — `test_chip_renderer_reads_count_not_object` must FAIL**

Run: `python3 -m pytest tests/test_erp_exp_contract.py -q`
Expected: FAIL (current JS still contains `' <b>' + tabs[k] + '</b>'`). `test_backend_tabs_shape_is_count_sar` PASSES (shape already `{count,sar}`).

- [ ] **Step 3: Fix the chip renderer**

In `finance/static/erp.js`, replace (currently ~line 2722-2724):
```javascript
    var chips = ['pending', 'approved', 'exported', 'verified', 'needs_action'].map(function (k) {
      return '<button class="fchip' + (expP.tab === k ? ' on' : '') + '" data-act="x-tab" data-tab="' + k + '">' +
        esc(t('x_' + k)) + (tabs[k] !== undefined ? ' <b>' + tabs[k] + '</b>' : '') + '</button>';
    }).join('');
```
with:
```javascript
    var chips = ['pending', 'approved', 'exported', 'verified', 'needs_action'].map(function (k) {
      var tb = tabs[k] || {}, cnt = (typeof tb === 'object') ? tb.count : tb, sar = (typeof tb === 'object') ? tb.sar : 0;
      return '<button class="fchip' + (expP.tab === k ? ' on' : '') + '" data-act="x-tab" data-tab="' + k + '">' +
        esc(t('x_' + k)) +
        (cnt !== undefined && cnt !== null ? ' <b>' + cnt + '</b>' : '') +
        (sar ? ' <i class="chip-sar">' + fmtAmt(sar) + '</i>' : '') + '</button>';
    }).join('');
```

- [ ] **Step 4: Add the quiet secondary style**

In `finance/static/erp.css`, add (reuse existing tokens — tinted neutral, never pure gray):
```css
.fchip .chip-sar{font-style:normal;font-size:11px;color:var(--text-3);margin-inline-start:2px;unicode-bidi:isolate}
.fchip.on .chip-sar{color:var(--text-2)}
```

- [ ] **Step 5: Run tests + JS gate**

Run:
```bash
node --check finance/static/erp.js
python3 -m pytest tests/test_erp_exp_contract.py -q
```
Expected: node clean; both chip tests PASS.

- [ ] **Step 6: Commit**

```bash
git add finance/static/erp.js finance/static/erp.css tests/test_erp_exp_contract.py
git commit -m "fix(erp): expense chips show the count, not [object Object]"
```

---

## Task 2: BUG 2 layer-2 — `_exp4_approve` becomes the honest source of truth

**Files:**
- Test: `tests/test_exp4_lifecycle.py` (created here, expanded in Task 5)
- Modify: `bot.py:_exp4_approve:11561-11574`

- [ ] **Step 1: Write the failing lifecycle test**

Create `tests/test_exp4_lifecycle.py`:
```python
# -*- coding: utf-8 -*-
"""V4 expense lifecycle state machine — synthetic, no network.
The screen that rots the most finally gets a test of its real transitions."""
import unittest
import bot


def mk(**kw):
    e = {"id": "L", "amount": 250.0, "expense_date": "2026-05-01",
         "apartment": "Ouja | شقة 7", "listing_id": 7001, "category": "صيانة"}
    e.update(kw)
    return e


class ApproveHonesty(unittest.TestCase):
    def test_pending_with_fields_approves_and_moves(self):
        e = mk(approval_status="pending_approval")
        ok, why = bot._exp4_approve(e)
        self.assertTrue(ok); self.assertEqual(why, "approved")
        self.assertEqual(bot._exp4_tab(e), "approved")

    def test_missing_fields_block_to_needs_edit(self):
        e = mk(approval_status="pending_approval", category="")
        ok, why = bot._exp4_approve(e)
        self.assertFalse(ok); self.assertTrue(why.startswith("needs_edit:"))
        self.assertNotEqual(bot._exp4_approval_status(e), "approved")

    def test_verified_is_refused_not_a_silent_noop(self):
        e = mk(hostaway_verified=True, hostaway_ref="55502", approval_status="approved")
        self.assertEqual(bot._exp4_tab(e), "verified")
        ok, why = bot._exp4_approve(e)
        self.assertFalse(ok); self.assertEqual(why, "already_verified")
        self.assertEqual(bot._exp4_tab(e), "verified")           # unchanged, honestly

    def test_exported_unverified_is_refused(self):
        e = mk(status="sent_unverified", hostaway_ref="60123", approval_status="approved",
               sent_at="2026-05-20T00:00:00")
        self.assertEqual(bot._exp4_tab(e), "exported")
        ok, why = bot._exp4_approve(e)
        self.assertFalse(ok); self.assertEqual(why, "already_exported")

    def test_split_parent_is_refused(self):
        e = mk(is_split_parent=True, approval_status="approved")
        ok, why = bot._exp4_approve(e)
        self.assertFalse(ok); self.assertEqual(why, "split_parent")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it — the refusal tests must FAIL**

Run: `python3 -m pytest tests/test_exp4_lifecycle.py -q`
Expected: `test_verified_is_refused...`, `test_exported_unverified...`, `test_split_parent...` FAIL (current code returns `(True,"approved")`). The pending + missing-fields tests PASS.

- [ ] **Step 3: Add the honesty guards**

In `bot.py`, replace the head of `_exp4_approve` (currently lines 11561-11567):
```python
def _exp4_approve(exp, by=""):
    """Pending/Needs-Edit → Approved (only when required fields are present)."""
    miss = _exp4_missing_required(exp)
    if miss:
        exp["approval_status"] = "needs_edit"
        _exp4_log(exp, "approve_blocked", actor=by, new="needs_edit", detail="missing: " + ",".join(miss))
        return False, "needs_edit:" + ",".join(miss)
```
with:
```python
def _exp4_approve(exp, by=""):
    """Pending/Needs-Edit → Approved. HONEST: refuses no-ops. _exp4_tab gives export-status
    precedence, so 'approving' an already-verified/exported/failed/duplicate/split expense
    would flip approval_status yet never move the row. Refuse with a reason instead of
    reporting a fake success (root cause of the 'press اعتماد → returns to متحققة' bug)."""
    if exp.get("hostaway_verified"):
        _exp4_log(exp, "approve_blocked", actor=by, detail="already_verified")
        return False, "already_verified"
    es = _exp4_export_status(exp)
    if es in ("export_requested", "exporting", "exported_not_verified"):
        _exp4_log(exp, "approve_blocked", actor=by, detail="already_exported")
        return False, "already_exported"
    if es in ("failed", "duplicate_found"):
        _exp4_log(exp, "approve_blocked", actor=by, detail=es)
        return False, "needs_recheck" if es == "failed" else "duplicate"
    if exp.get("is_split_parent"):
        _exp4_log(exp, "approve_blocked", actor=by, detail="split_parent")
        return False, "split_parent"
    miss = _exp4_missing_required(exp)
    if miss:
        exp["approval_status"] = "needs_edit"
        _exp4_log(exp, "approve_blocked", actor=by, new="needs_edit", detail="missing: " + ",".join(miss))
        return False, "needs_edit:" + ",".join(miss)
```
(The rest of the function — set `approved`, log, `return True, "approved"` — is unchanged.)

- [ ] **Step 4: Run it — all green**

Run: `python3 -m pytest tests/test_exp4_lifecycle.py -q`
Expected: all PASS.

- [ ] **Step 5: Compile + commit**

```bash
rm -rf __pycache__ && python3 -W error::SyntaxWarning -m py_compile bot.py
git add bot.py tests/test_exp4_lifecycle.py
git commit -m "fix(erp): approve refuses no-ops on terminal expenses (honest blocked reason)"
```

---

## Task 3: BUG 2 layer-2b — live tab counts on every action response (DRY)

**Files:**
- Modify: `bot.py` — NEW `_exp4_tab_counts` near `_exp4_overview_data:35900`; reuse in `_exp4_overview_data`; add `tabs` to `_api_exp4_approve:35972`, `_api_exp4_export:36014`, `_api_exp4_recheck:36030`, `_api_exp4_reject:35987`
- Test: `tests/test_exp4_lifecycle.py`

- [ ] **Step 1: Write the failing test (counts == rows; response carries tabs)**

Append to `tests/test_exp4_lifecycle.py`:
```python
class TabCounts(unittest.TestCase):
    def test_counts_equal_rows_per_tab(self):
        bot._expenses.clear()
        bot._expenses["p"] = mk(id="p", approval_status="pending_approval")
        bot._expenses["a"] = mk(id="a", approval_status="approved")
        bot._expenses["v"] = mk(id="v", hostaway_verified=True, hostaway_ref="9", approval_status="approved")
        counts = bot._exp4_tab_counts()
        self.assertEqual(counts["pending"]["count"], 1)
        self.assertEqual(counts["approved"]["count"], 1)
        self.assertEqual(counts["verified"]["count"], 1)
        # the overview must agree with the standalone counter
        ov = bot._exp4_overview_data(tab="pending")
        self.assertEqual(ov["tabs"], counts)
```

- [ ] **Step 2: Run — FAIL (`_exp4_tab_counts` undefined)**

Run: `python3 -m pytest tests/test_exp4_lifecycle.py::TabCounts -q`
Expected: FAIL with AttributeError.

- [ ] **Step 3: Extract the counter and reuse it**

In `bot.py`, insert ABOVE `_exp4_overview_data` (line 35900):
```python
def _exp4_tab_counts():
    """Single source of truth for the 5 lifecycle tab badges: {tab: {count, sar}}.
    Used by the overview AND returned on every action response so the chips stay live."""
    tabs = {k: {"count": 0, "sar": 0.0} for k in ("pending", "approved", "exported", "verified", "needs_action")}
    for e in _expenses.values():
        v = _exp4_view(e)
        t = v["tab"]
        if t in tabs:
            tabs[t]["count"] += 1
            tabs[t]["sar"] = round(tabs[t]["sar"] + v["amount_sar"], 2)
    return tabs
```
Then in `_exp4_overview_data`, replace the inline `tabs` construction + per-row increment with a single call. Change the opening:
```python
def _exp4_overview_data(tab="pending", q="", limit=120, offset=0):
    tabs = {k: {"count": 0, "sar": 0.0} for k in ("pending", "approved", "exported", "verified", "needs_action")}
    ql = (q or "").strip().lower()
    rows = []
    for e in _expenses.values():
        v = _exp4_view(e)
        t = v["tab"]
        if t == "archived":
            continue
        if t in tabs:
            tabs[t]["count"] += 1
            tabs[t]["sar"] = round(tabs[t]["sar"] + v["amount_sar"], 2)
        if t == tab:
```
to:
```python
def _exp4_overview_data(tab="pending", q="", limit=120, offset=0):
    tabs = _exp4_tab_counts()
    ql = (q or "").strip().lower()
    rows = []
    for e in _expenses.values():
        v = _exp4_view(e)
        t = v["tab"]
        if t == "archived":
            continue
        if t == tab:
```

- [ ] **Step 4: Return `tabs` from the four action handlers**

`_api_exp4_approve` — change `out = {"ok": True, "approved": [], "blocked": []}` so the final return carries counts. Replace `return _json(out)` (after `persist_state`) with:
```python
    out["tabs"] = _exp4_tab_counts()
    return _json(out)
```
Apply the identical `out["tabs"] = _exp4_tab_counts()` line immediately before `return _json(out)` in `_api_exp4_export` and `_api_exp4_recheck`. For `_api_exp4_reject`, change its return to:
```python
    return _json({"ok": True, "view": _exp4_view(e), "tabs": _exp4_tab_counts()})
```

- [ ] **Step 5: Run — green; compile**

Run:
```bash
python3 -m pytest tests/test_exp4_lifecycle.py -q
rm -rf __pycache__ && python3 -W error::SyntaxWarning -m py_compile bot.py
```
Expected: all PASS; compile clean.

- [ ] **Step 6: Commit**

```bash
git add bot.py tests/test_exp4_lifecycle.py
git commit -m "feat(erp): action responses carry live tab counts (DRY _exp4_tab_counts)"
```

---

## Task 4: BUG 2 layers 1+3 — tab-aware affordance + reconciling frontend

**Files:**
- Modify: `finance/static/erp.js` — NEW helpers; `expRowHtml`; `updateExpBulk`; `x-bulk-*` + `x-confirm-reject` + single handlers; `T.ar`/`T.en`

- [ ] **Step 1: Add block-reason i18n keys (parity-locked)**

In `T.ar` (inside the `ar:{...}` block, near the other `x_*` keys) add:
```javascript
      x_blk_already_verified: 'متحقق مسبقًا في Hostaway', x_blk_already_exported: 'مُصدّر — ما يحتاج اعتماد',
      x_blk_needs_recheck: 'فشل التصدير — أعد الفحص', x_blk_duplicate: 'مكرر في Hostaway', x_blk_split_parent: 'مصروف مقسّم — أدر الأبناء',
```
In `T.en` (matching position in `en:{...}`) add the twins:
```javascript
      x_blk_already_verified: 'Already verified in Hostaway', x_blk_already_exported: 'Exported — no approval needed',
      x_blk_needs_recheck: 'Export failed — recheck it', x_blk_duplicate: 'Duplicate in Hostaway', x_blk_split_parent: 'Split parent — manage its children',
```

- [ ] **Step 2: Add the single-source affordance + reconcile helpers**

In `finance/static/erp.js`, immediately above `function expSelectedIds()` (line 2586), add:
```javascript
  // ONE source of truth for "what bulk action does this tab afford".
  // pending/needs_action -> approve ; approved -> export ; exported/verified -> none (terminal).
  function expBulkAction(tab) {
    if (tab === 'pending' || tab === 'needs_action') return 'approve';
    if (tab === 'approved') return 'export';
    return '';
  }
  var EXP_BLK = { already_verified: 'x_blk_already_verified', already_exported: 'x_blk_already_exported',
    needs_recheck: 'x_blk_needs_recheck', duplicate: 'x_blk_duplicate', split_parent: 'x_blk_split_parent' };
  function expBlockMsg(list) {
    if (!list || !list.length) return '';
    var first = list[0] || {}, code = String(first.reason || '');
    var label = EXP_BLK[code] ? t(EXP_BLK[code])
      : (code.indexOf('needs_edit') === 0 ? t('x_missing') + code.slice(11).replace(/,/g, '، ') : code);
    return t('x_blocked_n').replace('{n}', list.length) + (label ? ' · ' + label : '');
  }
  // Patch the chip badges in place from a {tab:{count,sar}} map — keeps counts live after an action.
  function expApplyCounts(tabs) {
    if (!tabs) return;
    if (store.D.exp) store.D.exp.tabs = tabs;
    $$('#view .fchip').forEach(function (chip) {
      var k = chip.getAttribute('data-tab'); if (!k || !tabs[k]) return;
      var b = chip.querySelector('b'); if (b) b.textContent = tabs[k].count;
      var i = chip.querySelector('.chip-sar'); if (i) i.textContent = tabs[k].sar ? fmtAmt(tabs[k].sar) : '';
    });
  }
```

- [ ] **Step 3: Render the selection checkbox only on tabs with a bulk action**

In `expRowHtml`, replace (line 2614-2615):
```javascript
    return '<div class="wq-row xrow" data-id="' + esc(r.expense_id) + '">' +
      '<div class="c-sel"><input type="checkbox" data-act="x-sel" data-id="' + esc(r.expense_id) + '"></div>' +
```
with:
```javascript
    var selCell = expBulkAction(tab)
      ? '<div class="c-sel"><input type="checkbox" data-act="x-sel" data-id="' + esc(r.expense_id) + '"></div>'
      : '<div class="c-sel"></div>';
    return '<div class="wq-row xrow" data-id="' + esc(r.expense_id) + '">' +
      selCell +
```

- [ ] **Step 4: Make the bulk bar tab-aware**

Replace `updateExpBulk` (lines 2762-2773) with:
```javascript
  function updateExpBulk() {
    var ids = expSelectedIds();
    var bar = $('#xBulk');
    if (!bar) return;
    var action = expBulkAction(expP.tab);
    if (!action || !ids.length) { bar.hidden = true; bar.innerHTML = ''; return; }
    bar.hidden = false;
    var btn = action === 'export'
      ? '<button class="btn primary sm" data-act="x-bulk-export">' + esc(t('x_export')) + '</button>'
      : '<button class="btn primary sm" data-act="x-bulk-approve">' + esc(t('x_approve')) + '</button>';
    bar.innerHTML = '<b>' + ids.length + '</b> ' + esc(t('bulk_selected')) + ' ' + btn +
      ' <button class="btn ghost sm" data-act="x-bulk-clear">' + esc(t('bulk_clear')) + '</button>';
  }
```

- [ ] **Step 5: Make the bulk handler reconcile against the server result**

Replace the `x-bulk-approve`/`x-bulk-export` handler (lines 1609-1623) with:
```javascript
    else if (act === 'x-bulk-approve' || act === 'x-bulk-export') {
      var xids = expSelectedIds();
      if (!xids.length) return;
      el.disabled = true;
      var ep = act === 'x-bulk-approve' ? '/erp/api/exp/approve' : '/erp/api/exp/export';
      api(ep, { method: 'POST', body: { ids: xids } }).then(function (r) {
        var okIds = (r.approved || r.queued || []).map(function (o) { return o.id; });
        okIds.forEach(function (i) { expRemoveRow(i); });          // remove ONLY what the server moved
        var blocked = (r.blocked || r.skipped || []);
        expApplyCounts(r.tabs);                                    // chips stay live
        if (okIds.length) toast((act === 'x-bulk-approve' ? t('x_approved_n') : t('x_exported_ok')).replace('{n}', okIds.length), 'ok');
        if (blocked.length) toast(expBlockMsg(blocked), 'warn');
        var xb = $('#xBulk'); if (xb) { xb.hidden = true; xb.innerHTML = ''; }
        $$('.xrow input[type=checkbox]').forEach(function (c) { c.checked = false; });
        if (!document.querySelector('#xList .xrow')) loadExp();    // list drained -> show empty-state + fresh data
      }).catch(function (e) { el.disabled = false; toast(srvMsg(e) || t('act_failed'), 'err'); });
    }
```

- [ ] **Step 6: Make single reject reconcile (sibling C2 fix)**

Replace the `x-confirm-reject` handler body (lines 1591-1593):
```javascript
      api('/erp/api/exp/reject', { method: 'POST', body: { id: id, reason: rsn } }).then(function () {
        expRemoveRow(id, t('x_rejected_ok'));
      }).catch(function (e) { el.disabled = false; toast(srvMsg(e) || t('act_failed'), 'err'); });
```
with:
```javascript
      api('/erp/api/exp/reject', { method: 'POST', body: { id: id, reason: rsn } }).then(function (r) {
        var nt = (r.view && r.view.tab) || '';
        expApplyCounts(r.tabs);
        if (nt && nt !== expP.tab) { expRemoveRow(id, t('x_rejected_ok')); }   // left this tab
        else { toast(t('x_rejected_ok')); loadExp(); }                          // stays (e.g. needs_action) -> refresh in place
      }).catch(function (e) { el.disabled = false; toast(srvMsg(e) || t('act_failed'), 'err'); });
```

- [ ] **Step 7: Keep chips live after single approve/export/recheck**

In the single `x-approve` handler, change the success branch (line 1571) from:
```javascript
        if ((r.approved || []).length) { expRemoveRow(id, t('x_approved_ok')); }
```
to:
```javascript
        if ((r.approved || []).length) { expApplyCounts(r.tabs); expRemoveRow(id, t('x_approved_ok')); }
```
In the single `x-export` handler (line 1598), change:
```javascript
        if ((r.queued || []).length) expRemoveRow(id, t('x_exported_ok'));
```
to:
```javascript
        if ((r.queued || []).length) { expApplyCounts(r.tabs); expRemoveRow(id, t('x_exported_ok')); }
```
In the single `x-recheck` handler (line 1605), change:
```javascript
        if ((r.verified || []).length) expRemoveRow(id, t('x_verified_ok'));
```
to:
```javascript
        if ((r.verified || []).length) { expApplyCounts(r.tabs); expRemoveRow(id, t('x_verified_ok')); }
```
Also map the single-approve block reason to a friendly string — change line 1574 from:
```javascript
          var why = ((r.blocked || [])[0] || {}).reason || t('act_failed');
```
to:
```javascript
          var why = expBlockMsg(r.blocked) || t('act_failed');
```

- [ ] **Step 8: JS gate + structural check**

Run:
```bash
node --check finance/static/erp.js
python3 - <<'PY'
import pathlib
js = pathlib.Path("finance/static/erp.js").read_text("utf-8")
assert js.count("{") == js.count("}"), "brace imbalance"
assert js.count("(") == js.count(")"), "paren imbalance"
assert js.count("`") % 2 == 0, "backtick imbalance"
import esprima, re
for m in re.finditer(r"<script>(.*?)</script>", js, re.S):
    esprima.parseScript(m.group(1))
print("erp.js structural + parse OK")
PY
```
Expected: node clean; structural OK. (erp.js has no inline `<script>`; the loop is a no-op safety net — the `node --check` is the real JS gate.)

- [ ] **Step 9: Commit**

```bash
git add finance/static/erp.js
git commit -m "fix(erp): tab-aware bulk bar + reconcile approve/reject against server truth"
```

---

## Task 5: Lock the full V4 lifecycle (precedence matrix + gates)

**Files:**
- Modify: `tests/test_exp4_lifecycle.py`

- [ ] **Step 1: Add the precedence + gate tests**

Append to `tests/test_exp4_lifecycle.py`:
```python
class TabPrecedence(unittest.TestCase):
    def test_each_state_lands_in_the_right_tab(self):
        self.assertEqual(bot._exp4_tab(mk(approval_status="pending_approval")), "pending")
        self.assertEqual(bot._exp4_tab(mk(approval_status="approved")), "approved")
        self.assertEqual(bot._exp4_tab(mk(approval_status="approved", hostaway_verified=True, hostaway_ref="9")), "verified")
        self.assertEqual(bot._exp4_tab(mk(approval_status="approved", status="sent_unverified",
                                          hostaway_ref="9", sent_at="2026-05-20T00:00:00")), "exported")
        self.assertEqual(bot._exp4_tab(mk(approval_status="needs_edit", category="")), "needs_action")
        self.assertEqual(bot._exp4_tab(mk(approval_status="approved", is_split_parent=True)), "needs_action")
        self.assertEqual(bot._exp4_tab(mk(approval_status="rejected", archived=True)), "archived")

    def test_verified_precedence_beats_approval(self):
        # both flags set: export status (verified) must win over approval lane
        e = mk(approval_status="approved", hostaway_verified=True, hostaway_ref="9")
        self.assertEqual(bot._exp4_tab(e), "verified")


class ExportGate(unittest.TestCase):
    def test_export_refuses_non_approved(self):
        ok, why = bot._exp4_request_export(mk(approval_status="pending_approval"))
        self.assertFalse(ok); self.assertEqual(why, "needs_approval")

    def test_export_refuses_split_parent(self):
        ok, why = bot._exp4_request_export(mk(approval_status="approved", is_split_parent=True))
        self.assertFalse(ok); self.assertEqual(why, "split_parent_not_exportable")

    def test_export_accepts_approved(self):
        e = mk(id="okexp", approval_status="approved")
        ok, why = bot._exp4_request_export(e)
        self.assertTrue(ok)


class RecheckDryRun(unittest.TestCase):
    def test_dryrun_never_verifies(self):
        import asyncio
        orig = bot.EXPENSE_POST_DRYRUN
        bot.EXPENSE_POST_DRYRUN = True
        try:
            e = mk(approval_status="approved", hostaway_ref="9")
            self.assertFalse(asyncio.get_event_loop().run_until_complete(bot._exp4_verify(e)))
            self.assertNotEqual(bot._exp4_tab(e), "verified")
        finally:
            bot.EXPENSE_POST_DRYRUN = orig
```

- [ ] **Step 2: Run the full lifecycle suite**

Run: `python3 -m pytest tests/test_exp4_lifecycle.py -q`
Expected: all PASS. (If `_exp4_request_export` enqueues to a module deque, that's fine — the test only asserts the gate return value.)

- [ ] **Step 3: Commit**

```bash
git add tests/test_exp4_lifecycle.py
git commit -m "test(erp): lock V4 tab precedence, export gate, dry-run recheck"
```

---

## Task 6: Finish the contract guardrail (routes · data-act · i18n parity)

**Files:**
- Modify: `tests/test_erp_exp_contract.py`

- [ ] **Step 1: Add the structural contract tests**

Append to `tests/test_erp_exp_contract.py`:
```python
import shutil, subprocess, json

INIT = pathlib.Path("finance/__init__.py").read_text("utf-8")


class RouteContract(unittest.TestCase):
    def test_every_exp_api_called_is_registered(self):
        routes = set(re.findall(r'add_(?:get|post|put|delete)\(\s*"([^"]+)"', INIT))
        called = set(re.findall(r"""api\(\s*['"](/erp/api/exp[^'"?]*)""", JS))
        called |= set(re.findall(r"""['"](/erp/api/exp[a-zA-Z0-9/_-]*)\??['"]""", JS))
        for c in called:
            c = c.rstrip("/")
            self.assertTrue(c in routes or any(c == r.rstrip("/") for r in routes),
                            "JS calls unregistered route: " + c)


class DataActContract(unittest.TestCase):
    def test_every_data_act_token_is_handled(self):
        acts = set(re.findall(r'data-act="([^"]+)"', JS))
        # drop dynamically-built tokens (data-act="' + x + '...") — those are not literals
        acts = {a for a in acts if "'" not in a and "+" not in a}
        branch = set(re.findall(r"act === '([^']+)'", JS))
        matched = set(re.findall(r"""\[data-act=\\?["']([^"'\]]+)""", JS))
        handled = branch | matched
        dead = sorted(a for a in acts if a not in handled)
        self.assertEqual(dead, [], "dead data-act tokens (no handler): " + repr(dead))


class I18nParity(unittest.TestCase):
    def test_ar_en_parity_and_coverage(self):
        if not shutil.which("node"):
            self.skipTest("node not available")
        probe = r"""
const fs=require('fs');const js=fs.readFileSync('finance/static/erp.js','utf8');
const i=js.indexOf('var T = {');let d=0,end=-1;
for(let p=js.indexOf('{',i);p<js.length;p++){if(js[p]==='{')d++;else if(js[p]==='}'){d--;if(d===0){end=p+1;break;}}}
const T=eval('('+js.slice(js.indexOf('{',i),end)+')');
const ar=Object.keys(T.ar),en=Object.keys(T.en);
const used=new Set();const re=/\bt\(\s*['"]([A-Za-z0-9_]+)['"]\s*(\+)?/g;let m;
while((m=re.exec(js))){if(!m[2])used.add(m[1]);}
const arS=new Set(ar),enS=new Set(en);
console.log(JSON.stringify({onlyAr:ar.filter(k=>!enS.has(k)),onlyEn:en.filter(k=>!arS.has(k)),
  absentAr:[...used].filter(k=>!arS.has(k)),absentEn:[...used].filter(k=>!enS.has(k))}));
"""
        out = subprocess.check_output(["node", "-e", probe], cwd=".").decode()
        r = json.loads(out)
        self.assertEqual(r["onlyAr"], [], "AR keys missing an EN twin")
        self.assertEqual(r["onlyEn"], [], "EN keys missing an AR twin")
        self.assertEqual(r["absentAr"], [], "t() keys absent from T.ar (render literal key)")
        self.assertEqual(r["absentEn"], [], "t() keys absent from T.en")
```

- [ ] **Step 2: Run the full contract suite**

Run: `python3 -m pytest tests/test_erp_exp_contract.py -q`
Expected: all PASS (routes clean, no dead tokens, i18n parity — all verified during the audit).

- [ ] **Step 3: Commit**

```bash
git add tests/test_erp_exp_contract.py
git commit -m "test(erp): contract gate — routes, data-act handlers, i18n parity"
```

---

## Task 7: Design pass — quiet polish on the chips + bulk bar (impeccable / emil)

**Files:**
- Modify: `finance/static/erp.css`

- [ ] **Step 1: Verify press feedback + reduced-motion already present; add only what's missing**

Run: `grep -nE "scale\(\.97|scale\(0\.97|prefers-reduced-motion|cubic-bezier\(0\.23" finance/static/erp.css`
Then ensure these exist (add any missing, near the `.btn`/`.fchip` rules — do NOT animate the auto-refreshed `.xrow`/chip counts):
```css
.btn:active,.fchip:active{transform:scale(.97)}
.btn,.fchip{transition:transform .12s cubic-bezier(0.23,1,0.32,1),background-color .15s,border-color .15s}
@media (prefers-reduced-motion: reduce){.btn,.fchip{transition:none}.btn:active,.fchip:active{transform:none}}
```

- [ ] **Step 2: Before/after UI table (emil-design-eng requires it) — record in the commit body**

| Element | Before | After |
|---|---|---|
| Tab chip badge | `[object Object] متحققة` | `متحققة 7  ٤٬٢٠٠ ر.س` (count + quiet SAR subtotal) |
| Bulk bar on `verified` | "Approve" button (silent no-op) | no checkboxes, no bar (terminal) |
| Bulk bar on `exported` | "Approve" button (no-op) | no bulk approve (per-row recheck only) |
| Bulk approve w/ blocked | "Approved ✓" (lie) | "Approved N · blocked: <reason>" + live counts |
| Chips after any action | stale until reload | patched live from `r.tabs` |

- [ ] **Step 3: JS/CSS gate + commit**

```bash
node --check finance/static/erp.js
git add finance/static/erp.css
git commit -m "style(erp): chip SAR subtotal + press feedback honoring reduced-motion"
```

---

## Task 8: Update CLAUDE.md verification routine + Finance traps

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Extend the VERIFICATION ROUTINE block**

In `CLAUDE.md` under "VERIFICATION ROUTINE", after the `pyflakes` line add:
```
python3 -m pyflakes bot.py finance/*.py                      # finance package too
node --check finance/static/erp.js                           # SPA JS must parse (a bad token kills login)
python3 -m pytest tests/                                     # all tests incl. V4 lifecycle + ERP contract
```

- [ ] **Step 2: Add a "Finance ERP traps" note**

After the existing "TRAPS" list, add:
```
## Finance ERP (المركز المالي) traps — mirror of the dashboard traps
The ERP SPA is finance/static/erp.js (~4.7k lines, hand-written, NO build step). Same class
of outage as DASHBOARD_HTML: one bad token kills the whole SPA so the page won't even log in —
`node --check finance/static/erp.js` is now part of the routine.
1. Contract drift: erp.js must read the SHAPE bot.py returns. The tab badges are
   {count, sar} objects — read `.count` (rendering the object gives `[object Object]`).
   tests/test_erp_exp_contract.py locks this.
2. Optimistic UI must reconcile: never removeRow + success-toast on assumption. Remove only
   the ids the server returned (approved/queued/verified); patch chip counts from `r.tabs`.
3. Terminal-state affordances: _exp4_tab gives export-status precedence, so approving a
   verified/exported/split/failed expense is a no-op. _exp4_approve refuses these with a
   reason; the bulk bar (expBulkAction) only offers approve on pending/needs_action.
   tests/test_exp4_lifecycle.py locks the state machine.
4. Dry-run: EXPENSE_POST_DRYRUN makes export file-only — items legitimately stop at
   'exported' and never auto-verify. Surface it (the x_dryrun tag), never read it as failure.
```

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: finance ERP verification routine + traps (node --check, contract, lifecycle)"
```

---

## Task 9: Full verification gate + cleanup + push

**Files:** delete scratch files

- [ ] **Step 1: Run the COMPLETE gate**

```bash
rm -rf __pycache__
python3 -W error::SyntaxWarning -m py_compile bot.py
python3 -m pyflakes bot.py finance/*.py | grep -v "imported but unused" || true
node --check finance/static/erp.js
python3 - <<'PY'
import pathlib
js = pathlib.Path("finance/static/erp.js").read_text("utf-8")
assert js.count("{") == js.count("}") and js.count("(") == js.count(")") and js.count("`") % 2 == 0
print("erp.js structural OK")
PY
python3 -m pytest tests/ -q
```
Expected: every line clean/green; pytest count ≥ Task 0 floor + new tests.

- [ ] **Step 2: Remove the scratch harnesses (logic now lives in tests/)**

```bash
rm -f _finance_repro.py _finance_audit.py _i18n_cov.js
```

- [ ] **Step 3: Final commit + push (triggers Railway deploy)**

```bash
git add -A
git commit -m "chore: remove finance-hardening scratch harnesses"
git push
```

- [ ] **Step 4: Owner-facing confirmation (AR + EN) with the 3 things to click**

Provide a plain-language summary: what was broken (chips garbage + approve bounce-back), what changed, and the 3 checks — (1) every tab chip shows a number; (2) on متحققة there's no اعتماد button; (3) approving on المعلّقة moves items to المعتمدة and both counts update.

---

## Self-review

- **Spec coverage:** BUG 1 (T1), BUG 2 all three layers (T2 backend, T3 counts, T4 affordance+frontend), C2 sibling reject (T4.6), audit table (this doc), guardrails node-check (T8) + contract test (T1,T6) + lifecycle test (T2,T3,T5), CLAUDE.md (T8), design pass (T1,T7). ✓
- **No placeholders:** every code/test step shows the real code. ✓
- **Type/name consistency:** `_exp4_tab_counts` (T3) used in T3/T6; `expBulkAction`/`expApplyCounts`/`expBlockMsg`/`EXP_BLK` defined T4.2, used T4.3–4.7; block reason codes (`already_verified`/`already_exported`/`needs_recheck`/`duplicate`/`split_parent`) match between `_exp4_approve` (T2.3) and `EXP_BLK` (T4.2). ✓
```
