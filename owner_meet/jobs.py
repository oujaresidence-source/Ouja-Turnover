# -*- coding: utf-8 -*-
"""
owner_meet.jobs — the snapshot build runs HERE, on its own small pool, never on the web lane
(brief P9: the owner pages were slow before; a request thread must never wait on 12 statements).
Progress is written to meet_meetings (build_progress / build_step) so the tab can poll it.
"""

import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor

from . import db, snapshot
from .host import HOST

_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="meet-build")
_running = {}
_info = {}                     # mid -> {"queued": ts, "started": ts|None, "error": str|None}
_lock = threading.Lock()

ERR_GENERIC = "تعذّر تجهيز الاجتماع — حاول مرة ثانية، وإذا تكرر بلّغ الدعم"


def running(mid):
    with _lock:
        f = _running.get(int(mid))
        return f is not None and not f.done()


def start(mid, params):
    """Queue a build. -> False when one is already running for this meeting."""
    mid = int(mid)
    with _lock:
        f = _running.get(mid)
        if f is not None and not f.done():
            return False
        db.set_build(mid, state="building", progress=1, step="في الطابور", error="")
        _info[mid] = {"queued": time.time(), "started": None, "error": None}
        _running[mid] = _pool.submit(run, mid, params)
    return True


def queue_info(mid):
    """Where this build stands: {running, started, waiting_ahead, elapsed_s, error}. In memory only."""
    mid = int(mid)
    with _lock:
        me = dict(_info.get(mid) or {})
        f = _running.get(mid)
        live = {m: i for m, i in _info.items() if _running.get(m) is not None and not _running[m].done()}
    ahead = sum(1 for m, i in live.items() if m != mid and i.get("queued", 0) <= me.get("queued", 0))
    now = time.time()
    return {"running": bool(f is not None and not f.done()), "started": bool(me.get("started")),
            "waiting_ahead": ahead if not me.get("started") else 0,
            "elapsed_s": int(now - (me.get("started") or me.get("queued") or now)), "error": me.get("error")}


def run(mid, params, today=None):
    """Build + save a new snapshot version. Synchronous (tests call it directly). -> version | None."""
    with _lock:
        if int(mid) in _info:
            _info[int(mid)]["started"] = time.time()
    if HOST.user_priority:                           # Faisal is watching the bar: a person is waiting
        try:
            HOST.user_priority()
        except Exception:
            pass

    def progress(pct, step):
        try:                                         # a progress write must never kill the build
            db.set_build(mid, progress=max(1, min(99, int(pct))), step=step)
        except Exception as e:
            print("[owner_meet] progress write failed:", e)

    try:
        snap = snapshot.build(dict(params, meeting_id=mid), progress=progress, today=today)
        ver, sha = db.save_snapshot(mid, snap)
        db.set_build(mid, state="ready", progress=100, step="جاهز", error="")
        db.log_event(mid, "built", {"version": ver, "sha256": sha})
        return ver
    except ValueError as e:
        _fail(mid, str(e))
    except Exception as e:
        traceback.print_exc()
        _fail(mid, ERR_GENERIC, repr(e))
    return None


def _fail(mid, text_ar, detail=None):
    with _lock:
        if int(mid) in _info:
            _info[int(mid)]["error"] = detail or text_ar
    for _ in range(3):                               # brain.db can be busy for a moment; never leave «building»
        try:
            db.set_build(mid, state="error", step="", error=text_ar)
            return
        except Exception as e:
            print("[owner_meet] could not record the build error:", e)
            time.sleep(1)
