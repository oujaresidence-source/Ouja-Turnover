#!/usr/bin/env python3
# Offline screenshot harness for /monthly (عوجا بالشهر). Extracts MONTHLY_HTML from bot.py,
# injects synthetic data + a fetch/route stub, renders via cached Playwright chromium.
# Mirrors _elite_shots.py. Run: python3 _monthly_shots.py
import re, json, os
from urllib.parse import quote
from playwright.sync_api import sync_playwright

SRC = open('bot.py', encoding='utf-8').read()
HTML = re.search(r'MONTHLY_HTML = r"""(.*?)"""', SRC, re.S).group(1)


def img(w, h, c1, c2, c3):
    svg = (f"<svg xmlns='http://www.w3.org/2000/svg' width='{w}' height='{h}'>"
           f"<defs><linearGradient id='g' x1='0' y1='0' x2='1' y2='1'>"
           f"<stop offset='0' stop-color='{c1}'/><stop offset='.55' stop-color='{c2}'/>"
           f"<stop offset='1' stop-color='{c3}'/></linearGradient></defs>"
           f"<rect width='{w}' height='{h}' fill='url(#g)'/></svg>")
    return "data:image/svg+xml," + quote(svg)


HERO = img(1400, 900, '#26332b', '#3a4a3e', '#5e7b6b')
COVERS = [img(600, 400, '#2c3a30', '#5b6b5f', '#b27a4f'),
          img(600, 400, '#3a3026', '#7a6a52', '#caa765'),
          img(600, 400, '#243930', '#4a6256', '#9db08a'),
          img(600, 400, '#33272a', '#6e5a52', '#c0906a')]


def pricing(before, months, pct):
    after = round(before * (1 - pct))
    return {"before": before, "after": after, "saved": before - after, "pct": pct,
            "ceiling": 0.30, "per_month_before": round(before / months),
            "per_month_after": round(after / months), "months": months,
            "nights": months * 30, "move_in": "2026-07-05",
            "move_out": "2026-%02d-05" % (7 + months), "available": True, "estimated": False}


def card(i, name, area, cap, beds, baths, pm_before, quote=None):
    c = {"id": 100 + i, "slug": "ouja-%d" % i, "name_ar": name, "name_en": name,
         "area": area, "capacity": cap, "beds": beds, "baths": baths,
         "cover": COVERS[i % 4], "images": COVERS, "tags": [],
         "m_before": pm_before, "m_after": round(pm_before * 0.85), "m_pct": 0.15, "ceiling": 0.30,
         "amenities": ["واي فاي سريع", "مطبخ مجهّز", "تكييف", "غسالة", "مواقف خاصة", "دخول ذاتي"],
         "desc_ar": "شقة مفروشة مريحة في قلب الرياض، جاهزة للسكن الشهري بلمسة عوجا — "
                    "مساحات منظمة، دخول ذاتي، وكل ما تحتاجه لإقامة طويلة هادئة.",
         "addons": [{"key": "parking", "ar": "موقف خاص", "en": "Private parking",
                     "in_listing": True, "note": "مواقف خاصة"},
                    {"key": "entry", "ar": "دخول خاص / مستقل", "en": "Private entry",
                     "in_listing": True, "note": "دخول ذاتي"}]}
    if quote:
        c["quote"] = quote
    return c


CARDS = [card(0, "Ouja | شقة الملقا المفروشة", "الملقا", 4, 2, 2, 9000),
         card(1, "Ouja | استوديو النخيل الهادئ", "النخيل", 2, 0, 1, 5200),
         card(2, "Ouja | شقة حطين العائلية", "حطين", 6, 3, 2, 12500)]

DATED = [card(0, "Ouja | شقة الملقا المفروشة", "الملقا", 4, 2, 2, 9000, pricing(27000, 3, 0.20)),
         card(2, "Ouja | شقة حطين العائلية", "حطين", 6, 3, 2, 12500, pricing(37500, 3, 0.20))]

LISTING = card(0, "Ouja | شقة الملقا المفروشة", "الملقا", 4, 2, 2, 9000, pricing(27000, 3, 0.20))

CFG = {"hero": HERO, "whatsapp": "966500000000", "imgproxy": False,
       "default_pct": 0.15, "ceiling_pct": 0.30,
       "promo": {"on": True, "pct": 0.20, "label_ar": "عرض الصيف · خصم يصل ٢٠٪", "label_en": ""},
       "addons": [{"key": "parking", "ar": "موقف خاص", "en": "Private parking"},
                  {"key": "entry", "ar": "دخول خاص / مستقل", "en": "Private entry"}],
       "count": 14, "noo": [], "neighborhoods": []}

DATA = {"config": CFG, "listing": None}

PAGE = (HTML
        .replace("/*__MONTHLY_DATA__*/null", json.dumps(DATA, ensure_ascii=False))
        .replace("/*__MONTHLY_JSONLD__*/null", "null")
        .replace("__MONTHLY_TITLE__", "Ouja Monthly").replace("__MONTHLY_DESC__", "Ouja Monthly")
        .replace("__MONTHLY_OG__", "").replace("__MONTHLY_URL__", "https://ouja.test/monthly"))

FEAT = json.dumps({"ok": True, "results": CARDS, "auto": True}, ensure_ascii=False)
SEARCH = json.dumps({"ok": True, "results": DATED, "browse": False, "avail_error": False}, ensure_ascii=False)
LIST = json.dumps({"ok": True, "listing": LISTING}, ensure_ascii=False)
QUOTE = json.dumps({"ok": True, "quote": pricing(27000, 3, 0.20)}, ensure_ascii=False)


def run():
    out = "/tmp/monthly_shots"
    os.makedirs(out, exist_ok=True)
    with sync_playwright() as p:
        br = p.chromium.launch()
        for label, vw, vh, path in [("home_mobile", 390, 844, "/monthly"),
                                    ("home_desktop", 1280, 900, "/monthly"),
                                    ("search_desktop", 1280, 900, "/monthly/search?move_in=2026-07-05&months=3"),
                                    ("listing_mobile", 390, 844, "/monthly/ouja-0?move_in=2026-07-05&months=3"),
                                    ("listing_desktop", 1280, 900, "/monthly/ouja-0?move_in=2026-07-05&months=3")]:
            pg = br.new_page(viewport={"width": vw, "height": vh}, device_scale_factor=2)

            def route(r):
                u = r.request.url
                if "fonts.g" in u:
                    return r.continue_()
                if "/api/monthly/featured" in u:
                    return r.fulfill(status=200, content_type="application/json", body=FEAT)
                if "/api/monthly/search" in u:
                    return r.fulfill(status=200, content_type="application/json", body=SEARCH)
                if "/api/monthly/listing/" in u:
                    return r.fulfill(status=200, content_type="application/json", body=LIST)
                if "/api/monthly/quote" in u:
                    return r.fulfill(status=200, content_type="application/json", body=QUOTE)
                if "/api/stay/event" in u:
                    return r.fulfill(status=204, body="")
                if "ouja.test" in u:
                    return r.fulfill(status=200, content_type="text/html", body=PAGE)
                return r.continue_()

            pg.route("**/*", route)
            pg.goto("https://ouja.test" + path, wait_until="load")
            try:
                pg.wait_for_selector(".panel" if "listing" in label else ".card", timeout=6000)
            except Exception:
                pass
            pg.wait_for_timeout(900)
            pg.evaluate("document.querySelectorAll('.reveal').forEach(function(e){e.classList.add('in');});")
            pg.wait_for_timeout(700)
            f = os.path.join(out, "monthly_%s.png" % label)
            pg.screenshot(path=f, full_page=True)
            print("saved", f)
            pg.close()
        br.close()


if __name__ == "__main__":
    run()
    print("DONE")
