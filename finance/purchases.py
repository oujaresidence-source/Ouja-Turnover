# -*- coding: utf-8 -*-
"""
finance.purchases — «مشتريات الفريق» Team Purchases + عهدة (float) engine.

A team member records a purchase they made for the operation. It is paid one of two ways:

  • تحويل (Transfer): Finance approves, then transfers the money.
      status flow  قيد المراجعة (pending) → معتمد (approved) → تم التحويل (transferred)
      or Finance rejects with a reason → مرفوض (rejected).
  • عهدة (Float): the buyer paid from a company float they already hold; no transfer.
      On submit the amount is deducted from that holder's float balance.
      status  مدفوع من العهدة (float_paid).

Storage reuses brain.db (the proven NO-WAL / journal_mode=DELETE rules) via `brain.db.connect`,
exactly like schedule.db / watchdog.db. Tables: tp_people, tp_holders, tp_purchases, tp_ledger.

This module is pure Python and importable without a running bot — the aiohttp routes in
finance/__init__.py call these functions. The apartments picker is injected by the route layer
(it comes from bot.get_listings_map), so this module never imports bot.

Balance model (authoritative, ledger-derived):
    original  = holder.starting_balance                       (editable by Finance)
    remaining = original + Σ ledger.delta                     (every event is a signed ledger row)
    spent     = max(0, original − remaining)                  (float outstanding; settlement clears it)
    low       = remaining <= holder.low_threshold

Ledger deltas: purchase −amount · reversal +amount · adjust ±diff · topup +amount ·
settlement +(original − remaining_before)  (restores remaining to original).
"""

import datetime
import threading
from contextlib import closing

from brain import db as _bdb

# ---------------------------------------------------------------- schema

SCHEMA = """
CREATE TABLE IF NOT EXISTS tp_people (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    can_submit  INTEGER DEFAULT 1,       -- appears in «من أضاف الطلب» (Submitted by)
    can_buy     INTEGER DEFAULT 0,       -- appears in «من اشترى» (Buyer)
    sort_order  INTEGER DEFAULT 0,
    active      INTEGER DEFAULT 1,
    created_at  TEXT
);
CREATE TABLE IF NOT EXISTS tp_holders (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT NOT NULL,        -- «صاحب العهدة» float holder
    start_balance  REAL DEFAULT 0,       -- المبلغ الأصلي (starting), editable
    low_threshold  REAL DEFAULT 0,       -- low-balance warning line
    user_key       TEXT,                 -- links this float to a logged-in user (matches _req_actor name) for visibility
    sort_order     INTEGER DEFAULT 0,
    active         INTEGER DEFAULT 1,
    created_at     TEXT
);
CREATE TABLE IF NOT EXISTS tp_purchases (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    purchase_date     TEXT,              -- التاريخ
    item              TEXT,              -- اسم الغرض
    amount            REAL DEFAULT 0,    -- المبلغ (SAR)
    listing_id        INTEGER,           -- الشقة (Hostaway listingMapId; NULL = غير مخصص/عام)
    apartment_name    TEXT,              -- snapshot of the apartment name at submit time
    submitted_by      TEXT,              -- من أضاف الطلب
    buyer             TEXT,              -- من اشترى (تقي / أبو أمين)
    pay_source        TEXT,              -- 'transfer' | 'float'
    reason            TEXT,              -- سبب الشراء
    receipt_path      TEXT,              -- local file path of the uploaded receipt image (NULL = none)
    no_receipt_reason TEXT,              -- required when receipt_path is NULL
    holder_id         INTEGER,           -- صاحب العهدة (required when pay_source='float')
    status            TEXT,              -- pending|approved|transferred|rejected|float_paid|deleted
    reject_reason     TEXT,
    created_by        TEXT,              -- actor who logged it (for the edit/delete-own gate)
    approved_by       TEXT,  approved_at    TEXT,
    transferred_by    TEXT,  transferred_at TEXT,
    rejected_by       TEXT,  rejected_at    TEXT,
    created_at        TEXT,  updated_at     TEXT
);
CREATE TABLE IF NOT EXISTS tp_ledger (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    holder_id   INTEGER NOT NULL,
    kind        TEXT,                    -- purchase|reversal|adjust|topup|settlement
    delta       REAL DEFAULT 0,          -- signed change to the float balance
    purchase_id INTEGER,                 -- linked purchase (for purchase/reversal/adjust)
    note        TEXT,
    actor       TEXT,
    created_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_tp_purch_status ON tp_purchases(status);
CREATE INDEX IF NOT EXISTS idx_tp_purch_holder ON tp_purchases(holder_id);
CREATE INDEX IF NOT EXISTS idx_tp_ledger_holder ON tp_ledger(holder_id, id);
"""

# statuses ------------------------------------------------------------------
ST_PENDING = "pending"
ST_APPROVED = "approved"
ST_TRANSFERRED = "transferred"
ST_REJECTED = "rejected"
ST_FLOAT = "float_paid"
ST_DELETED = "deleted"

STATUS_LABELS = {
    ST_PENDING:     {"ar": "قيد المراجعة", "en": "Pending"},
    ST_APPROVED:    {"ar": "معتمد",        "en": "Approved"},
    ST_TRANSFERRED: {"ar": "تم التحويل",   "en": "Transferred"},
    ST_REJECTED:    {"ar": "مرفوض",        "en": "Rejected"},
    ST_FLOAT:       {"ar": "مدفوع من العهدة", "en": "Paid from float"},
}

PAY_TRANSFER = "transfer"
PAY_FLOAT = "float"

GENERAL_APT_AR = "غير مخصص / عام"   # apartment value for purchases not tied to a unit

# seeds (editable afterwards from the Manage panel — the single source of the name lists) -----
SEED_PEOPLE = [
    {"name": "أسيل",      "can_submit": 1, "can_buy": 0},
    {"name": "محمد",      "can_submit": 1, "can_buy": 0},
    {"name": "نورة",      "can_submit": 1, "can_buy": 0},
    {"name": "مآثر",      "can_submit": 1, "can_buy": 0},
    {"name": "ناصر",      "can_submit": 1, "can_buy": 0},
    {"name": "عهود",      "can_submit": 1, "can_buy": 0},
    {"name": "تقي",       "can_submit": 1, "can_buy": 1},
    {"name": "أبو أمين",  "can_submit": 1, "can_buy": 1},
]
SEED_HOLDERS = [
    {"name": "أسيل"},
    {"name": "محمد"},
    {"name": "تقي"},
    {"name": "أبو أمين"},
]


class TPError(Exception):
    """Business-rule violation — carries a bilingual message for the API envelope."""

    def __init__(self, code, ar, en=""):
        self.code = code
        self.ar = ar
        self.en = en or ar
        super().__init__(code)


# ---------------------------------------------------------------- db plumbing

_inited = set()
_init_lock = threading.Lock()


def _ensure():
    path = _bdb.db_path()
    if path in _inited:
        return
    with _init_lock:
        if path in _inited:
            return
        with closing(_bdb.connect()) as cx:
            cx.executescript(SCHEMA)
            cx.commit()
        _seed_if_empty()
        _inited.add(path)


def reset_init_cache():
    """Tests point brain.db at a throwaway file, then call this so the next query re-inits+seeds."""
    _inited.clear()


def now_iso():
    return datetime.datetime.utcnow().isoformat(timespec="seconds")


def _q(sql, args=()):
    with closing(_bdb.connect()) as cx:
        return [dict(r) for r in cx.execute(sql, args).fetchall()]


def _q1(sql, args=()):
    with closing(_bdb.connect()) as cx:
        r = cx.execute(sql, args).fetchone()
        return dict(r) if r else None


def _exec(sql, args=()):
    with closing(_bdb.connect()) as cx:
        cur = cx.execute(sql, args)
        cx.commit()
        return cur.lastrowid


def _seed_if_empty():
    with closing(_bdb.connect()) as cx:
        n = cx.execute("SELECT COUNT(*) c FROM tp_people").fetchone()[0]
        if not n:
            ts = now_iso()
            for i, p in enumerate(SEED_PEOPLE):
                cx.execute("INSERT INTO tp_people(name,can_submit,can_buy,sort_order,active,created_at) "
                           "VALUES(?,?,?,?,1,?)",
                           (p["name"], p.get("can_submit", 1), p.get("can_buy", 0), i, ts))
        n = cx.execute("SELECT COUNT(*) c FROM tp_holders").fetchone()[0]
        if not n:
            ts = now_iso()
            for i, h in enumerate(SEED_HOLDERS):
                cx.execute("INSERT INTO tp_holders(name,start_balance,low_threshold,user_key,sort_order,active,created_at) "
                           "VALUES(?,0,0,'',?,1,?)", (h["name"], i, ts))
        cx.commit()


# ---------------------------------------------------------------- readers: config / people

def people(active_only=True):
    _ensure()
    sql = "SELECT * FROM tp_people"
    if active_only:
        sql += " WHERE active=1"
    return _q(sql + " ORDER BY sort_order, id")


def submitters():
    return [p["name"] for p in people() if p.get("can_submit")]


def buyers():
    return [p["name"] for p in people() if p.get("can_buy")]


def holders(active_only=True):
    _ensure()
    sql = "SELECT * FROM tp_holders"
    if active_only:
        sql += " WHERE active=1"
    return _q(sql + " ORDER BY sort_order, id")


def holder(holder_id):
    _ensure()
    return _q1("SELECT * FROM tp_holders WHERE id=?", (int(holder_id),))


def holder_names():
    return [h["name"] for h in holders()]


# ---------------------------------------------------------------- balance math

def _to_num(x, default=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def holder_balance(holder_id):
    """{holder_id, name, original, spent, remaining, low, low_threshold}. Ledger-derived, authoritative."""
    h = holder(holder_id)
    if not h:
        return None
    original = _to_num(h.get("start_balance"))
    row = _q1("SELECT COALESCE(SUM(delta),0) s FROM tp_ledger WHERE holder_id=?", (int(holder_id),))
    delta = _to_num((row or {}).get("s"))
    remaining = original + delta
    spent = max(0.0, original - remaining)
    thr = _to_num(h.get("low_threshold"))
    return {
        "holder_id": h["id"], "name": h["name"],
        "original": round(original, 2), "spent": round(spent, 2),
        "remaining": round(remaining, 2), "low_threshold": round(thr, 2),
        "low": remaining <= thr,
    }


def all_balances():
    return [holder_balance(h["id"]) for h in holders()]


def _ledger_add(cx, holder_id, kind, delta, purchase_id=None, note="", actor=""):
    cx.execute("INSERT INTO tp_ledger(holder_id,kind,delta,purchase_id,note,actor,created_at) "
               "VALUES(?,?,?,?,?,?,?)",
               (int(holder_id), kind, round(float(delta), 2),
                purchase_id, note, actor, now_iso()))


def statement(holder_id):
    """كشف حساب العهدة — chronological ledger with a running remaining balance."""
    h = holder(holder_id)
    if not h:
        return None
    original = _to_num(h.get("start_balance"))
    rows = _q("SELECT * FROM tp_ledger WHERE holder_id=? ORDER BY id", (int(holder_id),))
    running = original
    out = []
    for r in rows:
        running += _to_num(r.get("delta"))
        pur = None
        if r.get("purchase_id"):
            pur = _q1("SELECT item,amount,purchase_date FROM tp_purchases WHERE id=?", (r["purchase_id"],))
        out.append({
            "id": r["id"], "kind": r["kind"], "delta": round(_to_num(r.get("delta")), 2),
            "balance": round(running, 2), "note": r.get("note") or "",
            "actor": r.get("actor") or "", "created_at": r.get("created_at") or "",
            "purchase": pur,
        })
    bal = holder_balance(holder_id)
    return {"holder": bal, "entries": out}


# ---------------------------------------------------------------- purchases: validation + create

def _clean_amount(x):
    v = _to_num(x, None)
    if v is None or v <= 0:
        raise TPError("bad_amount", "المبلغ لازم يكون رقم أكبر من صفر.", "Amount must be a positive number.")
    return round(v, 2)


def _valid_person(name, pool, label_ar, label_en):
    if not name or name not in pool:
        raise TPError("bad_person", "اختر %s من القائمة." % label_ar, "Pick a valid %s." % label_en)
    return name


def create_purchase(fields, actor="", apartment_resolver=None):
    """Create one purchase. `fields` is a plain dict (strings ok). `apartment_resolver(listing_id)->name`
    resolves the apartment snapshot name (injected by the route so this module stays bot-free).
    Returns the created row dict. Raises TPError on any rule violation."""
    _ensure()
    item = (fields.get("item") or "").strip()
    if not item:
        raise TPError("no_item", "اكتب اسم الغرض.", "Item name is required.")
    amount = _clean_amount(fields.get("amount"))
    pdate = (fields.get("purchase_date") or "").strip() or datetime.date.today().isoformat()

    submitted_by = _valid_person(fields.get("submitted_by"), set(submitters()), "من أضاف الطلب", "submitter")
    buyer = _valid_person(fields.get("buyer"), set(buyers()), "من اشترى", "buyer")

    pay_source = (fields.get("pay_source") or "").strip()
    if pay_source not in (PAY_TRANSFER, PAY_FLOAT):
        raise TPError("bad_pay", "اختر طريقة الدفع (تحويل أو عهدة).", "Choose a payment source (transfer or float).")

    reason = (fields.get("reason") or "").strip()

    # apartment: listing_id (int) or the general bucket
    lid = fields.get("listing_id")
    listing_id = None
    apartment_name = GENERAL_APT_AR
    if lid not in (None, "", "0", 0, "general"):
        try:
            listing_id = int(lid)
        except (TypeError, ValueError):
            raise TPError("bad_apartment", "اختر شقة صحيحة.", "Pick a valid apartment.")
        apartment_name = ""
        if apartment_resolver:
            apartment_name = apartment_resolver(listing_id) or ""
        if not apartment_name:
            apartment_name = str(listing_id)

    # receipt: image path OR a no-receipt explanation — never neither
    receipt_path = (fields.get("receipt_path") or "").strip() or None
    no_receipt_reason = (fields.get("no_receipt_reason") or "").strip() or None
    if not receipt_path and not no_receipt_reason:
        raise TPError("no_receipt", "أرفق صورة الفاتورة، أو اكتب سبب عدم وجود فاتورة.",
                      "Attach a receipt image, or write why there is no receipt.")

    holder_id = None
    if pay_source == PAY_FLOAT:
        holder_id = fields.get("holder_id")
        h = holder(holder_id) if holder_id not in (None, "", "0", 0) else None
        if not h:
            raise TPError("bad_holder", "اختر صاحب العهدة (لازم يكون أحد أصحاب العهدة).",
                          "Choose the float holder (must be one of the float holders).")
        holder_id = h["id"]
        status = ST_FLOAT
    else:
        status = ST_PENDING

    ts = now_iso()
    with closing(_bdb.connect()) as cx:
        cur = cx.execute(
            "INSERT INTO tp_purchases(purchase_date,item,amount,listing_id,apartment_name,submitted_by,buyer,"
            "pay_source,reason,receipt_path,no_receipt_reason,holder_id,status,created_by,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (pdate, item, amount, listing_id, apartment_name, submitted_by, buyer, pay_source, reason,
             receipt_path, no_receipt_reason, holder_id, status, actor, ts, ts))
        pid = cur.lastrowid
        if pay_source == PAY_FLOAT:
            _ledger_add(cx, holder_id, "purchase", -amount, purchase_id=pid,
                        note=item, actor=actor)
        cx.commit()
    return get_purchase(pid)


def get_purchase(pid):
    _ensure()
    return _q1("SELECT * FROM tp_purchases WHERE id=?", (int(pid),))


# ---------------------------------------------------------------- edit / delete (with float reversal)

def _assert_editable_by(p, actor, is_finance):
    """Backend edit/delete gate (NOT just UI-hiding).
      • transfer: only while pending; and only the creator or Finance.
      • float:    the creator or Finance (balance is adjusted safely on any change).
      • rejected/transferred/deleted: locked for everyone (Finance may still edit a
        transfer only while pending — once acted, it locks)."""
    st = p.get("status")
    if st == ST_DELETED:
        raise TPError("locked", "الطلب محذوف.", "This purchase is deleted.")
    if p.get("pay_source") == PAY_TRANSFER:
        if st != ST_PENDING:
            raise TPError("locked", "بعد ما تصرّفت المالية بالطلب صار مقفل — ما ينعدل ولا ينحذف.",
                          "Once Finance has acted, the purchase is locked.")
    if not is_finance and (p.get("created_by") or "") != (actor or "__none__"):
        raise TPError("forbidden", "تقدر تعدّل أو تحذف طلباتك أنت بس.",
                      "You can only edit or delete your own purchases.")


def edit_purchase(pid, fields, actor="", is_finance=False, apartment_resolver=None):
    p = get_purchase(pid)
    if not p:
        raise TPError("not_found", "ما لقينا الطلب.", "Purchase not found.")
    _assert_editable_by(p, actor, is_finance)

    updates = {}
    if "item" in fields:
        item = (fields.get("item") or "").strip()
        if not item:
            raise TPError("no_item", "اكتب اسم الغرض.", "Item name is required.")
        updates["item"] = item
    if "purchase_date" in fields and (fields.get("purchase_date") or "").strip():
        updates["purchase_date"] = fields["purchase_date"].strip()
    if "submitted_by" in fields:
        updates["submitted_by"] = _valid_person(fields.get("submitted_by"), set(submitters()),
                                                 "من أضاف الطلب", "submitter")
    if "buyer" in fields:
        updates["buyer"] = _valid_person(fields.get("buyer"), set(buyers()), "من اشترى", "buyer")
    if "reason" in fields:
        updates["reason"] = (fields.get("reason") or "").strip()
    if "listing_id" in fields:
        lid = fields.get("listing_id")
        if lid in (None, "", "0", 0, "general"):
            updates["listing_id"] = None
            updates["apartment_name"] = GENERAL_APT_AR
        else:
            try:
                lid = int(lid)
            except (TypeError, ValueError):
                raise TPError("bad_apartment", "اختر شقة صحيحة.", "Pick a valid apartment.")
            updates["listing_id"] = lid
            nm = (apartment_resolver(lid) if apartment_resolver else "") or str(lid)
            updates["apartment_name"] = nm
    if "receipt_path" in fields:
        updates["receipt_path"] = (fields.get("receipt_path") or "").strip() or None
    if "no_receipt_reason" in fields:
        updates["no_receipt_reason"] = (fields.get("no_receipt_reason") or "").strip() or None

    # receipt integrity after applying the intended values
    new_receipt = updates.get("receipt_path", p.get("receipt_path"))
    new_noreason = updates.get("no_receipt_reason", p.get("no_receipt_reason"))
    if not new_receipt and not new_noreason:
        raise TPError("no_receipt", "أرفق صورة الفاتورة، أو اكتب سبب عدم وجود فاتورة.",
                      "Attach a receipt image, or write why there is no receipt.")

    # amount / holder changes → adjust the float ledger so the balance stays exact
    old_amount = _to_num(p.get("amount"))
    new_amount = old_amount
    if "amount" in fields:
        new_amount = _clean_amount(fields.get("amount"))
        updates["amount"] = new_amount

    new_holder = p.get("holder_id")
    if p.get("pay_source") == PAY_FLOAT and "holder_id" in fields and fields.get("holder_id") not in (None, ""):
        h = holder(fields.get("holder_id"))
        if not h:
            raise TPError("bad_holder", "اختر صاحب العهدة.", "Choose the float holder.")
        new_holder = h["id"]
        updates["holder_id"] = new_holder

    ts = now_iso()
    with closing(_bdb.connect()) as cx:
        if p.get("pay_source") == PAY_FLOAT:
            if new_holder != p.get("holder_id"):
                # moved to a different float: give the old holder back, take from the new one
                _ledger_add(cx, p["holder_id"], "reversal", old_amount, purchase_id=pid,
                            note="نقل الطلب لعهدة ثانية", actor=actor)
                _ledger_add(cx, new_holder, "purchase", -new_amount, purchase_id=pid,
                            note=updates.get("item", p.get("item")), actor=actor)
            elif new_amount != old_amount:
                # same holder, amount changed: adjust by the difference
                _ledger_add(cx, p["holder_id"], "adjust", -(new_amount - old_amount), purchase_id=pid,
                            note="تعديل المبلغ", actor=actor)
        if updates:
            updates["updated_at"] = ts
            cols = ", ".join("%s=?" % k for k in updates)
            cx.execute("UPDATE tp_purchases SET %s WHERE id=?" % cols,
                       tuple(updates.values()) + (int(pid),))
        cx.commit()
    return get_purchase(pid)


def delete_purchase(pid, actor="", is_finance=False):
    p = get_purchase(pid)
    if not p:
        raise TPError("not_found", "ما لقينا الطلب.", "Purchase not found.")
    _assert_editable_by(p, actor, is_finance)
    with closing(_bdb.connect()) as cx:
        if p.get("pay_source") == PAY_FLOAT and p.get("holder_id"):
            # restore the deducted amount before removing the record
            _ledger_add(cx, p["holder_id"], "reversal", _to_num(p.get("amount")), purchase_id=pid,
                        note="حذف الطلب", actor=actor)
        cx.execute("UPDATE tp_purchases SET status=?, updated_at=? WHERE id=?",
                   (ST_DELETED, now_iso(), int(pid)))
        cx.commit()
    return True


# ---------------------------------------------------------------- transfer lifecycle (Finance only)

def approve(pid, by=""):
    p = get_purchase(pid)
    if not p:
        raise TPError("not_found", "ما لقينا الطلب.", "Purchase not found.")
    if p.get("pay_source") != PAY_TRANSFER:
        raise TPError("not_transfer", "طلبات العهدة ما تحتاج اعتماد.", "Float purchases don't need approval.")
    if p.get("status") != ST_PENDING:
        raise TPError("bad_state", "ما يمكن اعتماد الطلب من هذي الحالة.", "Can't approve from this state.")
    _exec("UPDATE tp_purchases SET status=?, approved_by=?, approved_at=?, updated_at=? WHERE id=?",
          (ST_APPROVED, by, now_iso(), now_iso(), int(pid)))
    return get_purchase(pid)


def reject(pid, by="", reason=""):
    reason = (reason or "").strip()
    if not reason:
        raise TPError("no_reason", "سبب الرفض مطلوب.", "A rejection reason is required.")
    p = get_purchase(pid)
    if not p:
        raise TPError("not_found", "ما لقينا الطلب.", "Purchase not found.")
    if p.get("pay_source") != PAY_TRANSFER:
        raise TPError("not_transfer", "طلبات العهدة ما تنرفض.", "Float purchases can't be rejected.")
    if p.get("status") not in (ST_PENDING, ST_APPROVED):
        raise TPError("bad_state", "ما يمكن رفض الطلب من هذي الحالة.", "Can't reject from this state.")
    _exec("UPDATE tp_purchases SET status=?, reject_reason=?, rejected_by=?, rejected_at=?, updated_at=? WHERE id=?",
          (ST_REJECTED, reason, by, now_iso(), now_iso(), int(pid)))
    return get_purchase(pid)


def mark_transferred(pid, by=""):
    p = get_purchase(pid)
    if not p:
        raise TPError("not_found", "ما لقينا الطلب.", "Purchase not found.")
    if p.get("pay_source") != PAY_TRANSFER:
        raise TPError("not_transfer", "طلبات العهدة ما لها تحويل.", "Float purchases have no transfer.")
    if p.get("status") != ST_APPROVED:
        raise TPError("bad_state", "لازم يتعمد الطلب أول قبل التحويل.", "Approve the purchase before transferring.")
    _exec("UPDATE tp_purchases SET status=?, transferred_by=?, transferred_at=?, updated_at=? WHERE id=?",
          (ST_TRANSFERRED, by, now_iso(), now_iso(), int(pid)))
    return get_purchase(pid)


# ---------------------------------------------------------------- float replenishment (Finance only)

def topup(holder_id, amount, by="", note=""):
    h = holder(holder_id)
    if not h:
        raise TPError("bad_holder", "ما لقينا صاحب العهدة.", "Float holder not found.")
    amt = _clean_amount(amount)
    with closing(_bdb.connect()) as cx:
        _ledger_add(cx, h["id"], "topup", amt, note=(note or "تعزيز العهدة"), actor=by)
        cx.commit()
    return holder_balance(h["id"])


def settle(holder_id, by="", note=""):
    """Restore the holder's remaining balance back to its original (تصفية العهدة)."""
    h = holder(holder_id)
    if not h:
        raise TPError("bad_holder", "ما لقينا صاحب العهدة.", "Float holder not found.")
    bal = holder_balance(h["id"])
    delta = round(bal["original"] - bal["remaining"], 2)
    if abs(delta) < 0.005:
        raise TPError("nothing_to_settle", "العهدة كاملة أصلاً — ما فيه شي نصفّيه.",
                      "The float is already full — nothing to settle.")
    with closing(_bdb.connect()) as cx:
        _ledger_add(cx, h["id"], "settlement", delta, note=(note or "تصفية العهدة"), actor=by)
        cx.commit()
    return holder_balance(h["id"])


# ---------------------------------------------------------------- config editors (Finance only)

def save_person(name, can_submit=1, can_buy=0, person_id=None, active=1):
    _ensure()
    name = (name or "").strip()
    if not name:
        raise TPError("no_name", "الاسم مطلوب.", "Name is required.")
    if person_id:
        _exec("UPDATE tp_people SET name=?, can_submit=?, can_buy=?, active=? WHERE id=?",
              (name, int(bool(can_submit)), int(bool(can_buy)), int(bool(active)), int(person_id)))
        return int(person_id)
    order = (_q1("SELECT COALESCE(MAX(sort_order),0)+1 n FROM tp_people") or {}).get("n", 0)
    return _exec("INSERT INTO tp_people(name,can_submit,can_buy,sort_order,active,created_at) VALUES(?,?,?,?,1,?)",
                 (name, int(bool(can_submit)), int(bool(can_buy)), order, now_iso()))


def save_holder(name, start_balance=None, low_threshold=None, user_key=None, holder_id=None, active=1):
    _ensure()
    if holder_id:
        h = holder(holder_id)
        if not h:
            raise TPError("bad_holder", "ما لقينا صاحب العهدة.", "Float holder not found.")
        sb = _to_num(start_balance, h.get("start_balance")) if start_balance is not None else h.get("start_balance")
        lt = _to_num(low_threshold, h.get("low_threshold")) if low_threshold is not None else h.get("low_threshold")
        uk = user_key if user_key is not None else h.get("user_key")
        nm = (name or h.get("name")).strip()
        _exec("UPDATE tp_holders SET name=?, start_balance=?, low_threshold=?, user_key=?, active=? WHERE id=?",
              (nm, sb, lt, uk or "", int(bool(active)), int(holder_id)))
        return int(holder_id)
    name = (name or "").strip()
    if not name:
        raise TPError("no_name", "الاسم مطلوب.", "Name is required.")
    order = (_q1("SELECT COALESCE(MAX(sort_order),0)+1 n FROM tp_holders") or {}).get("n", 0)
    return _exec("INSERT INTO tp_holders(name,start_balance,low_threshold,user_key,sort_order,active,created_at) "
                 "VALUES(?,?,?,?,?,1,?)",
                 (name, _to_num(start_balance), _to_num(low_threshold), user_key or "", order, now_iso()))


# ---------------------------------------------------------------- list / filter / summary

def list_purchases(filters=None, include_deleted=False):
    _ensure()
    filters = filters or {}
    where = []
    args = []
    if not include_deleted:
        where.append("status != ?")
        args.append(ST_DELETED)
    if filters.get("status"):
        where.append("status=?")
        args.append(filters["status"])
    if filters.get("pay_source"):
        where.append("pay_source=?")
        args.append(filters["pay_source"])
    if filters.get("submitted_by"):
        where.append("submitted_by=?")
        args.append(filters["submitted_by"])
    if filters.get("buyer"):
        where.append("buyer=?")
        args.append(filters["buyer"])
    if filters.get("holder_id"):
        where.append("holder_id=?")
        args.append(int(filters["holder_id"]))
    if filters.get("listing_id"):
        where.append("listing_id=?")
        args.append(int(filters["listing_id"]))
    if filters.get("date_from"):
        where.append("purchase_date>=?")
        args.append(filters["date_from"])
    if filters.get("date_to"):
        where.append("purchase_date<=?")
        args.append(filters["date_to"])
    sql = "SELECT * FROM tp_purchases"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY date(purchase_date) DESC, id DESC"
    rows = _q(sql, tuple(args))

    q = (filters.get("q") or "").strip().lower()
    if q:
        def hit(r):
            blob = " ".join(str(r.get(k) or "") for k in
                            ("item", "apartment_name", "submitted_by", "buyer", "reason"))
            return q in blob.lower()
        rows = [r for r in rows if hit(r)]
    return rows


def summary(filters=None):
    """SAR totals for the top cards. Counts + amounts per bucket."""
    rows = list_purchases(filters)
    out = {
        "pending":     {"count": 0, "sar": 0.0},
        "approved":    {"count": 0, "sar": 0.0},   # awaiting transfer
        "transferred": {"count": 0, "sar": 0.0},
        "float":       {"count": 0, "sar": 0.0},   # paid from float
    }
    for r in rows:
        amt = _to_num(r.get("amount"))
        st = r.get("status")
        if st == ST_PENDING:
            out["pending"]["count"] += 1
            out["pending"]["sar"] += amt
        elif st == ST_APPROVED:
            out["approved"]["count"] += 1
            out["approved"]["sar"] += amt
        elif st == ST_TRANSFERRED:
            out["transferred"]["count"] += 1
            out["transferred"]["sar"] += amt
        elif st == ST_FLOAT:
            out["float"]["count"] += 1
            out["float"]["sar"] += amt
    for v in out.values():
        v["sar"] = round(v["sar"], 2)
    return out


# ---------------------------------------------------------------- visibility

def visible_holder_ids(actor="", is_finance=False):
    """Backend visibility rule for float balances/statements:
        • Finance (admin/accountant) → ALL holders.
        • otherwise → only the holder linked to this logged-in user (tp_holders.user_key == actor name).
        • nobody else sees any balance."""
    if is_finance:
        return {h["id"] for h in holders()}
    a = (actor or "").strip()
    if not a:
        return set()
    return {h["id"] for h in holders() if (h.get("user_key") or "").strip() == a}


def can_see_holder(holder_id, actor="", is_finance=False):
    return int(holder_id) in visible_holder_ids(actor, is_finance)
