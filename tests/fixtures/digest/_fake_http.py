# -*- coding: utf-8 -*-
"""FakeHttp — the offline stand-in for digest.net_live. Same three functions, same
return shapes. `pages` maps url -> (status, content_type, body) where body is str for
text and bytes for binary; `redirects` maps url -> final url. Every call is recorded
in `.calls` so a test can prove a code path never touched the network."""
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def fixture(name):
    with open(os.path.join(HERE, name), encoding="utf-8") as fh:
        return fh.read()


class FakeHttp(object):
    def __init__(self, pages=None, redirects=None, head_status=None, permissive_head=False):
        self.pages = dict(pages or {})
        self.redirects = dict(redirects or {})
        self.head_status = dict(head_status or {})   # url -> status override for head()
        self.permissive_head = permissive_head       # offline dry runs: every https link "exists"
        self.calls = []

    def _final(self, url):
        return self.redirects.get(url, url)

    def _lookup(self, url):
        final = self._final(url)
        if final in self.pages:
            return final, self.pages[final]
        if url in self.pages:
            return final, self.pages[url]
        return final, (404, "text/html", "")

    def get_text(self, url, timeout=20):
        self.calls.append(("get_text", url))
        final, (status, ctype, body) = self._lookup(url)
        if isinstance(body, bytes):
            body = body.decode("utf-8", "replace")
        return status, final, ctype, body

    def head(self, url, timeout=12):
        self.calls.append(("head", url))
        final, (status, ctype, _) = self._lookup(url)
        if url in self.head_status:
            status = self.head_status[url]
        elif self.permissive_head and status == 404 and url.lower().startswith("https://"):
            status, ctype = 200, "text/html"
        return status, final, ctype

    def get_bytes(self, url, timeout=25, max_bytes=6000000):
        self.calls.append(("get_bytes", url))
        final, (status, ctype, body) = self._lookup(url)
        if isinstance(body, str):
            body = body.encode("utf-8")
        return status, final, ctype, body[:max_bytes]
