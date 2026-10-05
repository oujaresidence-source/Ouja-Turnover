# -*- coding: utf-8 -*-
"""PDF for «حساب المالك»: «كشف حساب ومطالبة مالية».

The owner picked the FULL-statement layout: per-unit table → every booking per
unit → expenses → manual lines → the amount due, in the house statement style
(cream/gold, fpdf2, the same Arabic font + shaping as the owner statements).

Two hard rules printed on the page itself:
  * this is NOT a tax invoice — the e-invoice is issued in Daftra (number quoted);
  * an unapproved month carries a red «مسودة — غير معتمدة» band.
Guests appear by initial only.
"""

from datetime import datetime

from . import api

_MONTHS_AR = ("يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو",
              "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر")
_KIND_AR = {"income": "دخل مضاف (عليه الرسوم)", "expense": "مصروف", "credit": "خصم لصالحك"}
_EXCL_AR = {"missing_payout": "مبلغ Airbnb ناقص", "non_airbnb": "حجز مو من Airbnb",
            "needs_channel_rule": "قناة غير معروفة", "missing_base": "مبلغ ناقص",
            "cancelled_no_money": "ملغي", "cancelled_money_signal": "ملغي — فيه إشارة دفع",
            "needs_review": "يحتاج مراجعة"}


def month_label(mkey):
    try:
        return "%s %s" % (_MONTHS_AR[int(mkey[5:7]) - 1], mkey[:4])
    except Exception:
        return mkey


def ar_date(iso):
    """'2026-10-15' → '15 أكتوبر 2026'. An ISO date inside Arabic text gets reordered
    by the bidi pass (it printed «15-10-2026»); words can't be misread."""
    s = str(iso or "")[:10]
    try:
        return "%d %s %s" % (int(s[8:10]), _MONTHS_AR[int(s[5:7]) - 1], s[:4])
    except (ValueError, IndexError):
        return s


def _n(x):
    try:
        return "{:,.2f}".format(float(x or 0))
    except (TypeError, ValueError):
        return "0.00"


def _dm(d):
    s = str(d or "")
    return (s[8:10] + "/" + s[5:7]) if len(s) >= 10 else s


def render(view):
    """view = ownerbill.month_view(...) → PDF bytes."""
    B = api.B
    from fpdf import FPDF
    fp = B._pdf_font()
    if not fp:
        raise B.PdfFontError("Arabic PDF font unavailable")
    sh = B._ar
    GOLD = (163, 119, 40); INK = (26, 24, 21); MUT = (128, 120, 106)
    CREAM = (250, 247, 240); LINE = (226, 218, 200); SOFT = (243, 236, 221); RED = (181, 59, 59)
    W, M = 210.0, 14.0
    U = W - 2 * M
    bld = view["building"]
    comp, totals, lines = view["comp"], view["totals"], view["lines"] or []
    sett = view.get("settings") or {}
    draft = not view.get("frozen")
    mlabel = month_label(view["month"])

    class Doc(FPDF):
        def footer(self):
            self.set_y(-11)
            self.set_font("ar", size=8)
            self.set_text_color(*MUT)
            self.set_x(M)
            self.cell(40, 5, "%d / {nb}" % self.page_no(), align="L")
            self.set_x(W - M - 120)
            self.cell(120, 5, sh("%s · %s" % (view["claim_no"], mlabel)), align="R")

    pdf = Doc(orientation="P", unit="mm", format="A4")
    pdf.alias_nb_pages()
    pdf.add_font("ar", "", fp, uni=True)
    pdf.set_auto_page_break(False)
    pdf.set_margins(M, 12, M)
    pdf.add_page()
    BOTTOM = 297 - 18

    def ensure(h, redraw=None):
        if pdf.get_y() + h > BOTTOM:
            pdf.add_page()
            pdf.set_y(14)
            if redraw:
                redraw()

    def txt(x, y, w, h, s, size=10, color=INK, align="R", fit=False):
        pdf.set_font("ar", size=size)
        pdf.set_text_color(*color)
        pdf.set_xy(x, y)
        s = str(s if s is not None else "")
        out = sh(s)
        if fit:
            # table cells never wrap: trim the LOGICAL text (before shaping) until it fits
            while s and pdf.get_string_width(out) > w - 0.5:
                s = s[:-2] if len(s) > 2 else ""
                out = sh(s + "…") if s else ""
        pdf.cell(w, h, out, align=align)

    # ---------------- header band ----------------
    pdf.set_fill_color(*CREAM); pdf.rect(0, 0, W, 44, "F")
    pdf.set_fill_color(*GOLD); pdf.rect(0, 44, W, 1.2, "F")
    txt(M, 8, U, 5, "OUJA RESIDENCE · عوجا للضيافة", 9.5, GOLD)
    txt(M, 14, U, 9, "كشف حساب ومطالبة مالية", 19, INK)
    meta1 = "المالك: %s   ·   العقار: %s (%d شقق على حساب المالك)   ·   الفترة: %s" % (
        sett.get("display_owner") or bld.get("owner"), bld.get("name_ar"), len(bld.get("units") or []), mlabel)
    txt(M, 25, U, 5, meta1, 9.5, MUT)
    meta2 = "رقم المطالبة: %s" % view["claim_no"]
    if view.get("version"):
        meta2 += "   ·   نسخة %s — اعتُمدت %s" % (view["version"], ar_date(view.get("approved_at")))
    meta2 += "   ·   الفاتورة الضريبية (دفترة): %s" % (view.get("daftra_no") or "—")
    txt(M, 31, U, 5, meta2, 9.5, MUT)
    y = 47
    if draft:
        pdf.set_fill_color(*RED); pdf.rect(0, 45.4, W, 6.2, "F")
        txt(M, 45.9, U, 5.2, "مسودة — غير معتمدة · ليست للإرسال", 9, (255, 255, 255), "C")
        y = 54

    # ---------------- totals box ----------------
    pdf.set_y(y + 2)
    rows = [("اللي حوّله Airbnb لك (%d حجز · %d ليلة)" % (totals["bookings"], totals["nights"]),
             totals["airbnb_income"], False)]
    if totals.get("manual_income"):
        rows.append(("دخل مضاف يدويًا (عليه الرسوم)", totals["manual_income"], False))
    rows.append(("رسوم عوجا (%s%%)" % _pct(bld.get("mgmt_pct")), totals["fee"], True))
    rows.append(("ضريبة القيمة المضافة %s%% على رسوم عوجا" % _pct(bld.get("vat_pct")), totals["vat"], True))
    rows.append(("المصاريف", totals["expenses"], True))
    if totals.get("credits"):
        rows.append(("خصومات لصالحك (تنخصم من المطلوب)", totals["credits"], True))
    box_h = 9 + 7 * len(rows) + 14
    by = pdf.get_y()
    pdf.set_fill_color(*CREAM); pdf.rect(M, by, U, box_h, "F")
    yy = by + 4
    for lbl, val, charge in rows:
        txt(M + U * 0.40, yy, U * 0.56, 7, lbl, 10.5, MUT)
        txt(M + 5, yy, U * 0.38, 7, _n(val) + " ر.س", 10.5, INK if charge else MUT, "L")
        yy += 7
    pdf.set_draw_color(*GOLD); pdf.line(M + 5, yy + 1.5, W - M - 5, yy + 1.5)
    due = float(totals["due"])
    big = "المبلغ المطلوب منك" if due >= 0 else "مبلغ مستحق لك"
    txt(M + U * 0.40, yy + 4, U * 0.56, 9, big, 13.5, GOLD)
    txt(M + 5, yy + 4, U * 0.38, 9, _n(abs(due)) + " ر.س", 14, GOLD, "L")
    pdf.set_y(by + box_h + 3)
    pay = []
    if view.get("due"):
        pay.append("يُستحق السداد قبل %s" % ar_date(view["due"]))
    else:
        pay.append("يُستحق السداد خلال 10 أيام من استلام الكشف")
    if sett.get("bank_text"):
        pay.append("التحويل إلى: %s" % sett["bank_text"])
    for p in pay:
        txt(M, pdf.get_y(), U, 6, p, 10, INK)
        pdf.set_y(pdf.get_y() + 6)

    # ---------------- generic table ----------------
    def section(title):
        ensure(16)
        pdf.set_y(pdf.get_y() + 3)
        txt(M, pdf.get_y(), U, 6, title, 11, GOLD)
        pdf.set_y(pdf.get_y() + 7)
        pdf.set_draw_color(*LINE); pdf.line(M, pdf.get_y() - 1, W - M, pdf.get_y() - 1)

    def table(cols, data, total=None):
        """cols: [(title, width_mm, align)] listed RIGHT→LEFT (RTL)."""
        def head():
            hy = pdf.get_y()
            pdf.set_fill_color(*SOFT); pdf.rect(M, hy, U, 6.5, "F")
            x = W - M
            for t, w, al in cols:
                x -= w
                txt(x + 1, hy + 0.6, w - 2, 5.5, t, 8.5, MUT, al)
            pdf.set_y(hy + 6.5)
        head()
        for i, r in enumerate(data):
            ensure(6, head)
            ry = pdf.get_y()
            x = W - M
            for (t, w, al), v in zip(cols, r):
                x -= w
                txt(x + 1, ry + 0.4, w - 2, 5.2, v, 9, INK, al, fit=True)
            pdf.set_draw_color(*LINE); pdf.line(M, ry + 6, W - M, ry + 6)
            pdf.set_y(ry + 6)
        if total:
            ensure(7, head)
            ry = pdf.get_y()
            pdf.set_fill_color(*CREAM); pdf.rect(M, ry, U, 6.5, "F")
            x = W - M
            for (t, w, al), v in zip(cols, total):
                x -= w
                txt(x + 1, ry + 0.6, w - 2, 5.4, v, 9.5, INK, al)
            pdf.set_y(ry + 7)

    # ---------------- per-unit summary ----------------
    section("ملخص الشقق")
    ucols = [("الشقة", 22, "R"), ("حجوزات", 18, "C"), ("ليالي", 16, "C"),
             ("حوّله Airbnb", 34, "L"), ("رسوم %s%%" % _pct(bld.get("mgmt_pct")), 28, "L"),
             ("ضريبة %s%%" % _pct(bld.get("vat_pct")), 24, "L"), ("مصاريف", 20, "L"), ("المطلوب", U - 162, "L")]
    urows = []
    for u in comp["units"]:
        urows.append([u["code"], str(u["n_bookings"]), str(u["nights"]), _n(u["income"]), _n(u["fee"]),
                      _n(u["vat"]), _n(u["expenses_total"]), _n(u["due"])])
    base = comp["base"]
    utot = ["المجموع", str(base["bookings"]), str(base["nights"]), _n(base["income"]), _n(base["fee"]),
            _n(base["vat"]), _n(base["expenses"]),
            _n(float(base["fee"]) + float(base["vat"]) + float(base["expenses"]))]
    table(ucols, urows, utot)
    notes = []
    for u in comp["units"]:
        if not u["n_bookings"]:
            notes.append("%s: ما فيه حجوزات على إعلانها الجديد هالشهر" % u["code"])
    for nline in notes:
        ensure(6)
        txt(M, pdf.get_y(), U, 5.5, nline, 8.5, MUT)
        pdf.set_y(pdf.get_y() + 5.5)

    # ---------------- bookings per unit ----------------
    bcols = [("الدخول", 26, "R"), ("الخروج", 26, "R"), ("ليالي", 18, "C"), ("الضيف", 30, "C"),
             ("رقم الحجز", 40, "C"), ("المبلغ", U - 140, "L")]
    for u in comp["units"]:
        if not u["bookings"]:
            continue
        section("حجوزات %s — %d حجز" % (u["code"], u["n_bookings"]))
        table(bcols, [[_dm(b["checkin"]), _dm(b["checkout"]), str(b["nights"]), b["guest"], str(b["id"] or ""),
                       _n(b["amount"])] for b in u["bookings"]],
              ["المجموع", "", str(u["nights"]), "", "", _n(u["income"])])

    # ---------------- excluded (transparency) ----------------
    excl = [(u["code"], x) for u in comp["units"] for x in u["excluded"]]
    if excl:
        section("حجوزات ما دخلت في الحساب — %d" % len(excl))
        table([("الشقة", 22, "R"), ("الدخول", 26, "R"), ("الخروج", 26, "R"), ("السبب", 60, "R"),
               ("رقم الحجز", U - 134, "C")],
              [[c, _dm(x["checkin"]), _dm(x["checkout"]), _EXCL_AR.get(x["reason"], x["reason"]), str(x["id"] or "")]
               for c, x in excl])

    # ---------------- expenses ----------------
    exps = [e for u in comp["units"] for e in u["expenses"]]
    if exps:
        section("المصاريف — %d" % len(exps))
        table([("التاريخ", 24, "R"), ("الشقة", 20, "R"), ("البند", U - 74, "R"), ("المبلغ", 30, "L")],
              [[_dm(e["date"]), e["unit"], (e.get("category") or "") + ((" — " + e["description"]) if e.get("description") else ""),
                _n(e["amount"])] for e in exps],
              ["", "", "المجموع", _n(sum(float(e["amount"]) for e in exps))])

    # ---------------- manual lines ----------------
    if lines:
        section("بنود يدوية — %d" % len(lines))
        table([("النوع", 34, "R"), ("الشقة", 18, "R"), ("البند", 56, "R"), ("السبب", U - 136, "R"),
               ("المبلغ", 28, "L")],
              [[_KIND_AR.get(l["kind"], l["kind"]), l.get("unit") or "—", l["label"], l.get("reason") or "",
                _n(l["amount"])] for l in lines])

    # ---------------- terms + legal note ----------------
    ensure(30)
    pdf.set_y(pdf.get_y() + 5)
    pdf.set_draw_color(*GOLD); pdf.line(M, pdf.get_y(), W - M, pdf.get_y())
    pdf.set_y(pdf.get_y() + 2)
    foot = [
        "أساس الحساب: %s%% من المبلغ اللي حوّله Airbnb لك، والنظافة على عوجا، والمصاريف بتكلفتها، "
        "وضريبة القيمة المضافة %s%% على رسوم عوجا فقط." % (_pct(bld.get("mgmt_pct")), _pct(bld.get("vat_pct"))),
        "يدخل الحجز في الشهر حسب يوم دخول الضيف. الحجوزات على إعلاناتنا القديمة تبقى في كشفك المعتاد.",
        "هذا كشف حساب ومطالبة مالية وليس فاتورة ضريبية. الفاتورة الضريبية الإلكترونية رقم %s صادرة من نظام دفترة."
        % (view.get("daftra_no") or "—"),
        "أُنشئ %s الساعة %s" % (ar_date(datetime.now(B.TZ).date().isoformat()), datetime.now(B.TZ).strftime("%H:%M")),
    ]
    for f in foot:
        ensure(6)
        txt(M, pdf.get_y(), U, 5.5, f, 8.5, MUT)
        pdf.set_y(pdf.get_y() + 5.5)
    out = pdf.output()
    return bytes(out)


def _pct(x):
    try:
        v = float(x)
        return ("%d" % v) if v == int(v) else ("%s" % v)
    except (TypeError, ValueError):
        return str(x)
