# -*- coding: utf-8 -*-
"""
aqd.engine — PURE rules for «العقود». No I/O: the template text, the CSS and the font block
arrive as arguments (aqd.files loads them), so every rule here is testable with plain strings.

  build_context()  answers -> the 22 template values (owner grammar, units table, settings)
  render()         ONE regex pass; a missing key raises KeyError; no '{{' may survive
  fill_slots()     the three overlays a frozen document keeps open (banner, two signatures)
  evidence_html()  «سجل التوقيع الإلكتروني» — the certificate page appended to signed PDFs
  can()            the state machine (draft → sent → opened → verified → signed_owner → completed)
  name_similarity  typed name vs the signer's name, after Arabic normalisation

THE FREEZE: a sent contract is rendered once with the banner and both signature blocks left as
HTML-comment markers. doc_sha256 hashes those bytes. Everything a party agrees to is inside the
hash; only the watermark (which must disappear once the owner approves the template) and the
signatures (which by definition come later) are filled at display time. Every user value is
HTML-escaped AND brace-escaped, so it can neither forge a marker nor re-expand a placeholder.
"""

import datetime
import difflib
import hashlib
import html as _html
import re
import unicodedata

from . import catalogue

PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")
SLOT = {k: "<!--aqd:%s-->" % k for k in ("version_banner", "sig_owner", "sig_operator")}
KEYS = ("font_css", "contract_css", "contract_ref", "template_version", "date_g", "date_h", "weekday",
        "version_banner", "op_pct", "owner_rows", "owner_refer", "op_rep_full", "op_cr_expiry",
        "op_fal_no", "op_fal_expiry", "unit_rows", "jamiya", "platform_proof", "sig_owner",
        "sig_operator", "brand_name", "brand_reg")

WEEKDAYS_AR = ("الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد")

STATUS_AR = {
    "draft": "مسودة", "sent": "أُرسل", "opened": "فُتح", "verified": "تحقّق العميل",
    "signed_owner": "وقّع العميل", "completed": "مكتمل", "expired": "منتهي", "void": "ملغى",
}

# transition -> (allowed FROM statuses, TO status)
TRANSITIONS = {
    "edit": ({"draft"}, "draft"),
    "send": ({"draft"}, "sent"),
    "open": ({"sent"}, "opened"),
    "verify": ({"sent", "opened"}, "verified"),
    "sign": ({"verified"}, "signed_owner"),
    "countersign": ({"signed_owner"}, "completed"),
    "void": ({"draft", "sent", "opened", "verified"}, "void"),
    "expire": ({"sent", "opened", "verified"}, "expired"),
    "resend": ({"expired"}, "sent"),
}

REFUSAL_AR = {
    "void": "هذا العقد أُلغي",
    "expired": "انتهت صلاحية الرابط",
    "completed": "العقد مكتمل — ما يتعدّل",
    "signed_owner": "العميل وقّع العقد — ما يتعدّل",
}


# ------------------------------------------------------------------ escaping + formats

def h(v):
    """HTML-escape a user value AND neutralise braces: a value of '{{op_pct}}' prints literally."""
    s = _html.escape("" if v is None else str(v), quote=True)
    return s.replace("{", "&#123;").replace("}", "&#125;")


def _d(v):
    if isinstance(v, datetime.datetime):
        return v.date()
    if isinstance(v, datetime.date):
        return v
    try:
        return datetime.date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def date_g(v):
    d = _d(v)
    return ("%02d/%02d/%04dم" % (d.day, d.month, d.year)) if d else "—"


def date_h(v):
    d = _d(v)
    if not d:
        return "—"
    try:
        from hijridate import Gregorian
        hj = Gregorian(d.year, d.month, d.day).to_hijri()
        return "%02d/%02d/%04dهـ" % (hj.day, hj.month, hj.year)
    except Exception:
        return "—"


def weekday_ar(v):
    d = _d(v)
    return WEEKDAYS_AR[d.weekday()] if d else "—"


def num(n):
    """1050 -> '1,050'; 22.5 -> '22.5'."""
    if n is None:
        return "—"
    if isinstance(n, float) and not n.is_integer():
        return ("%g" % n)
    return "{:,}".format(int(n))


def pct(n):
    return "—" if n is None else ("%g" % n)


def last4(s):
    s = re.sub(r"\s", "", str(s or ""))
    return s[-4:] if len(s) >= 4 else ""


def mask(s):
    l4 = last4(s)
    return ("••••••" + l4) if l4 else ""


# ------------------------------------------------------------------ the parties

def is_company(a):
    return a.get("client_kind") == "company"


def female(a):
    """Grammar switch: a woman, or a company (شركة is feminine)."""
    return is_company(a) or a.get("gender") == "f"


def client_name(a):
    return (a.get("company_name") if is_company(a) else a.get("full_name")) or ""


def signer(a):
    """Who opens the link and signs: {name, secret (full), kind}. The secret's last 4 is the
    identity check; the name is what the typed name is compared with."""
    if is_company(a):
        return {"name": a.get("rep_name") or "", "secret": a.get("cr_number") or "", "kind": "cr"}
    if a.get("signer") == "agent":
        return {"name": a.get("agent_name") or "", "secret": a.get("agent_id") or "", "kind": "id"}
    return {"name": a.get("full_name") or "", "secret": a.get("id_number") or "",
            "kind": "alnum" if a.get("id_type") == "other" else "id"}


def honorific(a):
    if is_company(a):
        return "شركة"
    return "الأستاذة" if a.get("gender") == "f" else "الأستاذ"


def greeting_name(a):
    if is_company(a) or a.get("signer") == "agent":
        return signer(a)["name"]
    parts = (a.get("full_name") or "").split()
    return parts[0] if parts else ""


ID_LABEL = {"nid": "رقم الهوية الوطنية", "iqama": "رقم الإقامة", "other": "رقم الهوية / الجواز"}


def _row(k, v_html):
    return '<tr><td class="k">%s</td><td>%s</td></tr>' % (h(k), v_html)


def _mobile(a):
    return '<span dir="ltr">%s</span>' % h(a.get("mobile") or "—")


def _vat(a):
    if a.get("vat_registered") == "yes" and a.get("vat_number"):
        return h(a["vat_number"])
    return "غير مسجلة" if female(a) else "غير مسجل"


def owner_rows(a):
    rows = []
    if is_company(a):
        rows.append(_row("الاسم النظامي", h(a.get("company_name"))))
        rows.append(_row("السجل التجاري / الرقم الموحد", h(a.get("cr_number"))))
        rows.append(_row("الرقم الضريبي", _vat(a)))
        rows.append(_row("الجوال", _mobile(a)))
        rows.append(_row("البريد", h(a.get("email") or "—")))
        rows.append(_row("العنوان الوطني", h(a.get("nat_address") or "—")))
        if a.get("rep_capacity") == "authorized":
            cap = "%s — مفوّض بالتوقيع بموجب %s" % (h(a.get("rep_name")), h(a.get("auth_ref")))
        else:
            cap = "%s — مدير الشركة" % h(a.get("rep_name"))
        rows.append(_row("الممثل وصفته", cap))
        return "".join(rows)
    f = a.get("gender") == "f"
    rows.append(_row("الاسم الكامل", h(a.get("full_name"))))
    rows.append(_row(ID_LABEL.get(a.get("id_type"), "رقم الهوية"), h(a.get("id_number"))))
    rows.append(_row("الرقم الضريبي", _vat(a)))
    rows.append(_row("الجوال", _mobile(a)))
    rows.append(_row("البريد", h(a.get("email") or "—")))
    rows.append(_row("العنوان الوطني", h(a.get("nat_address") or "—")))
    rows.append(_row("الصفة", "مالكة أصلية" if f else "مالك أصلي"))
    if a.get("signer") == "agent":
        rows.append(_row("يمثلها في التوقيع" if f else "يمثله في التوقيع",
                         "%s، هوية رقم %s، بموجب الوكالة رقم %s وتاريخ %s"
                         % (h(a.get("agent_name")), h(a.get("agent_id")), h(a.get("wakala_no")),
                            h(date_g(a.get("wakala_date"))))))
    return "".join(rows)


def owner_refer(a):
    pron = "إليها" if female(a) else "إليه"
    return "ويُشار %s في هذا العقد بـ«المالك» أو «الطرف الأول»." % pron


# ------------------------------------------------------------------ the units

def _city(u):
    if u.get("city") == "other":
        return u.get("city_other") or "—"
    return catalogue.CITY_AR.get(u.get("city"), "—")


def _rooms(u):
    b = str(u.get("bedrooms") or "")
    if b == "0":
        return "استوديو"
    if b == "5":
        return "5+ غرف"
    if b == "1":
        return "غرفة واحدة"
    if b == "2":
        return "غرفتان"
    return ("%s غرف" % b) if b else "—"


def _licence(u):
    st = u.get("licence_status")
    if st == "issued":
        return "%s — ينتهي %s" % (h(u.get("licence_no")), h(date_g(u.get("licence_expiry"))))
    if st == "pending":
        return "قيد الإصدار — لا يبدأ التشغيل قبل صدوره"
    if st == "not_applied":
        return "لم يُقدَّم بعد — لا يبدأ التشغيل قبل صدوره"
    return "—"


def unit_rows(a):
    out = []
    for i, u in enumerate(a.get("units") or []):
        fee = catalogue.fee_value(u)
        minp = u.get("min_price")
        cells = [
            h(u.get("label") or "A%d" % (i + 1)),
            "%s — حي %s" % (h(_city(u)), h(u.get("district") or "—")),
            "%s / %s" % (h(catalogue.UNIT_TYPE_AR.get(u.get("unit_type"), "—")), h(_rooms(u))),
            h(u.get("deed_no") or "—"),
            _licence(u),
            ("%s ريال" % num(fee)) if fee is not None else "—",
            ("%s ريال" % num(minp)) if isinstance(minp, (int, float)) else (
                catalogue.UNSET_AR if minp == catalogue.UNSET_AR else "—"),
            h(u.get("blocked_text")) if u.get("blocked") == "set" else "لا يوجد",
            h(date_g(u.get("delivery_date"))),
        ]
        out.append("<tr>" + "".join("<td>%s</td>" % c for c in cells) + "</tr>")
    return "".join(out)


JAMIYA = {
    "none": "☑ (أ) لا توجد جمعية ملاك مسجلة في منصة «ملاك»",
    "ok": "☑ (ب) توجد جمعية ملاك ونظامها الأساس خالٍ من أي نص يمنع التأجير اليومي أو يقيده",
}


def jamiya(a):
    return JAMIYA.get(a.get("jamiya"), "— لم يُحدَّد بعد —")


# ------------------------------------------------------------------ operator + overlays

def op_rep_full(s):
    return ("%s، وكيلاً عن الشركة بموجب الوكالة رقم %s وتاريخ %s الصادرة عبر منصة ناجز، "
            "والمتضمنة إبرام العقود وتوقيعها عن الشركة"
            % (h(s.get("op_rep_name") or "—"), h(s.get("op_wakala_no") or "—"),
               h(s.get("op_wakala_date") or "—")))


def banner_html(approved):
    return "" if approved else '<div class="ver draft">نموذج غير معتمد للتوقيع — للاطلاع فقط</div>'


def sig_owner_label(a):
    if is_company(a):
        return "%s — عن %s" % (a.get("rep_name") or "", a.get("company_name") or "")
    if a.get("signer") == "agent":
        return "%s — وكيلاً عن %s" % (a.get("agent_name") or "", a.get("full_name") or "")
    return a.get("full_name") or ""


def sig_owner_html(label, png_b64=None, signed_at=None, typed_name=None):
    if not png_b64:
        return "الاسم: %s<br>التوقيع: بانتظار التوقيع" % h(label)
    return ("الاسم: %s<br>الاسم المكتوب عند التوقيع: %s<br>التوقيع:"
            '<img class="sigimg" alt="توقيع المالك" src="data:image/png;base64,%s">'
            "التاريخ: %s" % (h(label), h(typed_name or label), png_b64, h(signed_at or "—")))


def sig_operator_html(rep_name, sig_b64=None, stamp_b64=None, signed_at=None, operator=None):
    from .config import OPERATOR_NAME
    head = "%s<br>الممثل: %s<br>" % (h(operator or OPERATOR_NAME), h(rep_name or "—"))
    if not sig_b64:
        return head + "التوقيع: بانتظار توقيع المشغّل"
    out = head + 'التوقيع:<img class="sigimg" alt="توقيع المشغّل" src="data:image/png;base64,%s">' % sig_b64
    if stamp_b64:
        out += 'الختم:<img class="sigimg" alt="ختم المشغّل" src="data:image/png;base64,%s">' % stamp_b64
    return out + "التاريخ: %s" % h(signed_at or "—")


# ------------------------------------------------------------------ context + render

def build_context(a, *, ref, created, settings, font_css, contract_css, template_version,
                  approved=False, frozen=True, banner=None):
    """The 22 values. frozen=True leaves the three overlays as markers (the stored document);
    frozen=False fills them for a one-off preview."""
    s = settings or {}
    ctx = {
        "font_css": font_css,
        "contract_css": contract_css,
        "contract_ref": h(ref),
        "template_version": h(template_version),
        "date_g": date_g(created),
        "date_h": date_h(created),
        "weekday": weekday_ar(created),
        "op_pct": h(pct(catalogue.op_pct_value(a))),
        "owner_rows": owner_rows(a),
        "owner_refer": owner_refer(a),
        "op_rep_full": op_rep_full(s),
        "op_cr_expiry": h(s.get("op_cr_expiry") or "—"),
        "op_fal_no": h(s.get("op_fal_no") or "—"),
        "op_fal_expiry": h(s.get("op_fal_expiry") or "—"),
        "unit_rows": unit_rows(a),
        "jamiya": jamiya(a),
        "platform_proof": h(s.get("platform_proof") or "—"),
        "brand_name": h(s.get("brand_name") or "—"),
        "brand_reg": h(s.get("brand_reg") or "—"),
    }
    if frozen:
        ctx.update({k: v for k, v in SLOT.items()})
    else:
        ctx["version_banner"] = banner if banner is not None else banner_html(approved)
        ctx["sig_owner"] = sig_owner_html(sig_owner_label(a))
        ctx["sig_operator"] = sig_operator_html(s.get("op_rep_name"))
    return ctx


def render(template, ctx):
    out = PLACEHOLDER.sub(lambda m: ctx[m.group(1)], template)
    if "{{" in out:
        raise ValueError("unfilled placeholder left in the contract")
    return out


def fill_slots(frozen_html, *, version_banner="", sig_owner="", sig_operator=""):
    out = frozen_html
    for k, v in (("version_banner", version_banner), ("sig_owner", sig_owner),
                 ("sig_operator", sig_operator)):
        out = out.replace(SLOT[k], v, 1)
    return out


def doc_hash(data):
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def contract_ref(cid, year):
    return "OUJA-CT-%04d-%04d" % (int(year), int(cid))


# ------------------------------------------------------------------ evidence page

EVIDENCE_ROWS = (
    ("ref", "مرجع العقد"), ("doc_sha256", "بصمة المستند (SHA-256)"),
    ("template_version", "إصدار النموذج"), ("created", "أنشأه / متى"),
    ("sent_at", "أُرسل الرابط"), ("first_open", "أول فتح / عدد مرات الفتح"),
    ("verified_at", "اجتاز التحقق من الهوية"), ("signed_at", "وقّع العميل (توقيت الرياض)"),
    ("signed_at_utc", "وقّع العميل (UTC)"), ("typed_name", "الاسم المكتوب"),
    ("id_last4", "آخر 4 من الهوية / السجل"), ("ip", "عنوان IP"), ("ua", "المتصفح / الجهاز"),
    ("link_id", "معرّف الرابط"), ("countersigned", "وقّع المشغّل / متى"),
)


def evidence_html(ev):
    rows = "".join(_row(label, '<span dir="auto">%s</span>' % h(ev.get(k) or "—"))
                   for k, label in EVIDENCE_ROWS)
    return ('<div class="evidence"><h2 class="art">سجل التوقيع الإلكتروني</h2>'
            '<p class="small">وُقّع هذا العقد إلكترونياً عبر رابط خاص بالموقّع بعد التحقق من هويته، '
            'وتطابق بصمة المستند أعلاه النسخة المجمّدة لحظة إرسال الرابط.</p>'
            '<table class="kv">%s</table></div>' % rows)


def append_evidence(doc, ev):
    i = doc.rfind("</body>")
    block = evidence_html(ev)
    return (doc[:i] + block + doc[i:]) if i >= 0 else doc + block


# ------------------------------------------------------------------ template routing (R2)

def template_for(clean):
    """-> (template name, None) or (None, Arabic reason). Pure: config.TEMPLATES is data.
    An old draft without account_model counts as 'owner' only when VAT-registered."""
    from . import config
    kind = (clean or {}).get("client_kind")
    model = (clean or {}).get("account_model")
    if not model and (clean or {}).get("vat_registered") == "yes":
        model = "owner"
    if kind == "company":
        return None, catalogue.COMPANY_REASON
    if kind != "individual":
        return None, "اختر نوع العميل"
    if model == "ouja":
        return None, catalogue.OUJA_REASON
    if model != "owner":
        return None, catalogue.MODEL_MISSING_REASON
    name = config.template_for_key(kind, model)
    return (name, None) if name else (None, catalogue.OUJA_REASON)


# ------------------------------------------------------------------ state machine

def _iso_to_dt(s):
    try:
        return datetime.datetime.fromisoformat(str(s))
    except (TypeError, ValueError):
        return None


def is_expired(c, now_utc_iso):
    if (c.get("status") or "") not in TRANSITIONS["expire"][0]:
        return False
    exp, now = _iso_to_dt(c.get("expires_at")), _iso_to_dt(now_utc_iso)
    return bool(exp and now and now > exp)


def effective_status(c, now_utc_iso=None):
    st = c.get("status") or "draft"
    if now_utc_iso and is_expired(c, now_utc_iso):
        return "expired"
    return st


def can(transition, c, now_utc_iso=None):
    """-> (ok, Arabic reason). Pure: the caller persists."""
    if transition not in TRANSITIONS:
        return False, "إجراء غير معروف"
    st = effective_status(c, now_utc_iso)
    allowed, _to = TRANSITIONS[transition]
    if st in allowed:
        return True, ""
    if transition == "void" and st in ("signed_owner", "completed"):
        return False, "العقد موقّع — ما يُلغى من النظام"
    if transition == "resend" and st != "expired":
        return False, "الإعادة للروابط المنتهية فقط"
    if transition == "countersign" and st != "signed_owner":
        return False, "العميل ما وقّع للحين"
    return False, REFUSAL_AR.get(st) or "الإجراء غير متاح في حالة «%s»" % STATUS_AR.get(st, st)


def target(transition):
    return TRANSITIONS[transition][1]


# ------------------------------------------------------------------ names

_DIAC = re.compile("[" + "".join(chr(c) for c in range(0x064B, 0x0653)) + chr(0x0670) + chr(0x0640) + "]")


def norm_name(s):
    s = unicodedata.normalize("NFKC", str(s or ""))
    s = _DIAC.sub("", s)
    s = s.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ى", "ي").replace("ة", "ه")
    return " ".join(s.lower().split())


def name_similarity(a, b):
    a, b = norm_name(a), norm_name(b)
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


# ------------------------------------------------------------------ privacy

def masked_answers(clean):
    """The DB copy: every ID number reduced to ••••••1234 (PDPL). The full values live only in
    the contract files under $STATE_DIR/aqd/<id>/."""
    out = dict(clean)
    for k in catalogue.ID_KEYS:
        if out.get(k):
            out[k] = mask(out[k])
    return out
