# -*- coding: utf-8 -*-
"""digest.net_live — the ONE file in the package that opens a socket.

bot.py wires this module as HOST.http; every collector, the link verifier and the
artwork fetcher call HOST.require("http") and never `requests` directly, so the whole
pipeline runs offline in tests with a fake that has the same three functions
(tests/fixtures/digest/_fake_http.py). tests/test_digest_nonetwork.py greps the package
to keep it that way."""

import time

import requests

# Browser-compatible but honest: it names us and links to us. Verified 2026-09-02 on
# platinumlist / elcinema / saff / kooora; a bare "OujaDigest/1.0" was bounced by
# Platinumlist's Queue-it safety net. We never impersonate a real browser.
UA = "Mozilla/5.0 (compatible; OujaDigest/1.0; +https://oujares.com)"
HEADERS = {"User-Agent": UA, "Accept-Language": "ar,en;q=0.8",
           "Accept": "text/html,application/xhtml+xml,image/*;q=0.9,*/*;q=0.5"}
RETRY_ON = (429, 500, 502, 503, 504)
TRIES = 3

_session = None


def _s():
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update(HEADERS)
    return _session


def _ctype(resp):
    return (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()


def _retrying(fn):
    last = None
    for n in range(TRIES):
        try:
            r = fn()
        except requests.RequestException as e:
            last = e
            time.sleep(1.5 * (n + 1))
            continue
        if r.status_code in RETRY_ON and n < TRIES - 1:
            r.close()
            time.sleep(1.5 * (n + 1))
            continue
        return r
    if last is not None:
        raise last
    raise RuntimeError("net_live: exhausted retries")


def _decode(r):
    """saff.com.sa declares utf-8 but serves cp1256; trust the bytes, not the header."""
    raw = r.content
    enc = r.encoding or "utf-8"
    try:
        txt = raw.decode(enc, "replace")
    except LookupError:
        txt = raw.decode("utf-8", "replace")
    if txt.count("\ufffd") > max(20, len(txt) // 200):
        for alt in ("cp1256", "utf-8"):
            try:
                cand = raw.decode(alt, "replace")
            except LookupError:
                continue
            if cand.count("\ufffd") < txt.count("\ufffd"):
                txt = cand
    return txt


def get_text(url, timeout=20):
    """-> (status, final_url, content_type, text)."""
    r = _retrying(lambda: _s().get(url, timeout=timeout, allow_redirects=True))
    try:
        return r.status_code, r.url, _ctype(r), _decode(r)
    finally:
        r.close()


def head(url, timeout=12):
    """-> (status, final_url, content_type). HEAD first; a 405/403/501 falls back to a
    one-byte ranged GET, because some CDNs refuse HEAD but serve the page fine."""
    r = _retrying(lambda: _s().head(url, timeout=timeout, allow_redirects=True))
    try:
        if r.status_code in (403, 405, 501):
            r.close()
            r = _retrying(lambda: _s().get(url, timeout=timeout, allow_redirects=True,
                                           headers={"Range": "bytes=0-0"}, stream=True))
            status = 200 if r.status_code == 206 else r.status_code
            return status, r.url, _ctype(r)
        return r.status_code, r.url, _ctype(r)
    finally:
        r.close()


def get_bytes(url, timeout=25, max_bytes=6000000):
    """-> (status, final_url, content_type, bytes). Stops reading past max_bytes."""
    r = _retrying(lambda: _s().get(url, timeout=timeout, allow_redirects=True, stream=True))
    try:
        buf = bytearray()
        for chunk in r.iter_content(65536):
            buf.extend(chunk)
            if len(buf) > max_bytes:
                break
        return r.status_code, r.url, _ctype(r), bytes(buf)
    finally:
        r.close()
