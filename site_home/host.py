# -*- coding: utf-8 -*-
"""
site_home.host — the one bridge to bot.py (same DI pattern as business/ and schedule/).
bot.py calls site_home.wire({...}) once at web-server start.
"""


class _Host:
    web = None          # aiohttp web module
    email = ""          # bot.OUJA_CONTACT_EMAIL — used when SITE_IDENTITY["email"] is empty
    whatsapp = ""       # bot.STAY_WHATSAPP — used when SITE_IDENTITY["phone"] is empty

    _wired = False

    def require(self, attr):
        v = getattr(self, attr, None)
        if v is None:
            raise RuntimeError("site_home used '%s' before site_home.wire()" % attr)
        return v


HOST = _Host()


def wire(caps):
    for k, v in (caps or {}).items():
        setattr(HOST, k, v)
    HOST._wired = True
    return HOST
