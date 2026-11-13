# -*- coding: utf-8 -*-
"""
hatif.engine — PURE rules: the webhook signature, phone normalisation and the reply text.

The reply lists ONLY units the site search returned as available WITH a price for those exact
dates. A unit the search could not confirm is never listed, and "could not check" is never
worded as "nothing available". Prices are the site's (before tax and Airbnb's fee), so the
text says so. The bot never claims a booking: the guest finishes in Airbnb.
Owner rule (2026-11-13): never state how many apartments Ouja has — not the total, not per
area, not "N more". The reply names units; it never counts them.
"""
import hashlib
import hmac
import re


def verify_signature(secret, raw, signature):
    """X-Voxa-Signature = lowercase hex HMAC-SHA256 of the RAW body, keyed with the channel's
    webhook secret. Fails closed: no secret or no signature ⇒ False."""
    if not secret or not signature or raw is None:
        return False
    try:
        if isinstance(raw, str):
            raw = raw.encode("utf-8")
        want = hmac.new(str(secret).encode("utf-8"), raw, hashlib.sha256).hexdigest()
        return hmac.compare_digest(want, str(signature).strip().lower())
    except Exception:
        return False


_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def normalize_phone(raw):
    """Digits only, Saudi numbers as 9665XXXXXXXX. None when it is not a phone number."""
    d = re.sub(r"\D", "", str(raw or "").translate(_AR_DIGITS))
    if d.startswith("00"):
        d = d[2:]
    if d.startswith("9660"):
        d = "966" + d[4:]
    if len(d) == 10 and d.startswith("05"):
        d = "966" + d[1:]
    elif len(d) == 9 and d.startswith("5"):
        d = "966" + d
    return d if len(d) >= 8 else None


def mask(text, limit=300):
    """What we keep or show of a guest's message: trimmed, long digit runs (phones, ids) hidden."""
    s = re.sub(r"\d{8,}", "•••", str(text or "").translate(_AR_DIGITS))
    return s[:limit]


def _dm(iso):
    try:
        y, m, d = iso.split("-")
        return "%d/%d" % (int(d), int(m))
    except Exception:
        return str(iso)


def nights_label(n):
    n = int(n or 0)
    if n == 1:
        return "ليلة وحدة"
    if n == 2:
        return "ليلتين"
    if 3 <= n <= 10:
        return "%d ليالي" % n
    return "%d ليلة" % n


def _money(v):
    try:
        return "{:,}".format(int(round(float(v))))
    except (TypeError, ValueError):
        return ""


def search_link(site_host, req):
    return "%s/apartments/search?check_in=%s&check_out=%s" % (site_host, req["check_in"], req["check_out"])


def pick_units(req, out):
    """(listable units, something_unknown?) from a _gw_search result."""
    results = list((out or {}).get("results") or [])
    unknown = bool((out or {}).get("avail_error"))
    want_beds = req.get("bedrooms") if not req.get("type") else None
    units = []
    for u in results:
        if want_beds:
            try:
                if int(u.get("bedrooms") or 0) != int(want_beds):
                    continue
            except (TypeError, ValueError):
                continue
        if u.get("available") is True and u.get("est_total"):
            units.append(u)
        elif u.get("available") is not False:
            unknown = True                     # shown by the site as «تعذر تحديث التوفر»
    return units, unknown


def build_reply(req, out, site_host, limit=6):
    link = search_link(site_host, req)
    span = "من %s إلى %s (%s)" % (_dm(req["check_in"]), _dm(req["check_out"]), nights_label(req["nights"]))
    units, unknown = pick_units(req, out)
    if not units:
        if unknown:
            return ("ما قدرت أتأكد من التوفر %s الحين 🙏\n"
                    "جرّب بعد دقايق، أو شف المتاح مباشرة:\n%s" % (span, link))
        return ("ما لقيت شقة متاحة %s 🙏\n"
                "جرّب تواريخ ثانية، أو شف كل الشقق:\n%s" % (span, link))
    lines = ["المتاح %s:" % span, ""]
    for u in units[:limit]:
        name = str(u.get("name_ar") or u.get("name_en") or "").strip()[:48]
        bits = [name]
        if u.get("area"):
            bits.append(str(u["area"]).strip()[:24])
        price = "%s ر.س" % _money(u.get("est_total"))
        if int(req["nights"] or 0) > 1 and u.get("est_avg"):
            price += " (%s لليلة)" % _money(u.get("est_avg"))
        bits.append(price)
        lines.append("• " + " — ".join(b for b in bits if b))
        lines.append("%s/apartments/%s" % (site_host, u.get("id")))
    lines.append("")
    more = len(units) - limit
    if more > 0:
        lines.append("وفيه غيرها متاحة، الكل هنا: %s" % link)      # owner rule: never state how many
    elif unknown:
        lines.append("فيه شقق ما قدرت أتأكد منها الحين، الكل هنا: %s" % link)
    if req.get("assumed_nights"):
        lines.append("حسبتها ليلة وحدة. إذا تبي أكثر اكتب عدد الليالي.")
    lines.append("السعر تقريبي قبل الضريبة ورسوم Airbnb. افتح رابط الشقة وكمّل الحجز من Airbnb.")
    return "\n".join(lines)[:4000]


_HELP = {
    "no_dates": ("اكتب تاريخ الدخول وعدد الليالي عشان أشيك لك المتاح 🤍\n"
                 "مثال: 20/11 ليلتين\nأو: الخميس 3 ليالي غرفتين"),
    "past": "التاريخ اللي كتبته فات 🙏 اكتب تاريخ جاي، مثال: 20/11 ليلتين",
    "bad_range": "تاريخ الخروج لازم يكون بعد الدخول 🙏 مثال: من 20/11 إلى 22/11",
    "too_far": "أقدر أشيك لك لين سنة قدام 🙏 اكتب تاريخ أقرب.",
    "monthly": ("للشهري والمدد الطويلة عندنا عرض خاص 🤝\n"
                "اكتب: تاريخ البداية · كم شهر · كم غرفة · الحي المفضل، وفريق الحجوزات يرسل لك العرض."),
}

ACK = "لحظة أشيك لك المتاح 🔎"
HANDOFF = "أحولك لأحد من الفريق يخدمك 🤝"


def help_text(reason):
    return _HELP.get(reason) or _HELP["no_dates"]
