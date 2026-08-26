# -*- coding: utf-8 -*-
"""
cp.host — the single bridge between the cp package and bot.py.

bot.py calls cp.wire({...}) once at web-server start, exactly as business/ and
schedule/ do. Nothing in this package imports bot.
"""


class _Host:
    web = None                # aiohttp web module
    json_response = None      # _json(data, status=200)
    save_json = None          # _save_json(name, obj) -> bool
    load_json = None          # _load_json(name, default)
    notify = None             # optional (payload) -> None  Discord push
    base_url = ""             # PUBLIC_BASE_URL
    links = None              # {"wa":..., "email":...}
    pdf_path = ""             # CP_PDF_PATH, absolute or repo-relative
    default_lang = "ar"       # CP_DEFAULT_LANG
    english_ready = False     # flip when the English edition exists
    redirect_business = False  # CP_REDIRECT_BUSINESS — /business 301 -> /cp
    listing_photos = None     # (listing_id) -> {"photo":..., "srcset":...}

    _wired = False


HOST = _Host()


def wire(caps):
    for k, v in (caps or {}).items():
        setattr(HOST, k, v)
    HOST._wired = True
    return HOST
