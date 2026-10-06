# -*- coding: utf-8 -*-
"""
owner_meet.jobs — the snapshot build runs HERE, on its own small pool, never on the web lane
(brief P9: the owner pages were slow before; a request thread must never wait on 12 statements).
Progress is written to meet_meetings (build_progress / build_step) so the tab can poll it.
"""

import threading
import traceback
from concurrent.futures import ThreadPoolExecutor

from . import db, snapshot

_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="meet-build")
_running = {}
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
        _running[mid] = _pool.submit(run, mid, params)
    return True


def run(mid, params, today=None):
    """Build + save a new snapshot version. Synchronous (tests call it directly). -> version | None."""
    def progress(pct, step):
        db.set_build(mid, progress=max(1, min(99, int(pct))), step=step)

    try:
        snap = snapshot.build(dict(params, meeting_id=mid), progress=progress, today=today)
        ver, sha = db.save_snapshot(mid, snap)
        db.set_build(mid, state="ready", progress=100, step="جاهز", error="")
        db.log_event(mid, "built", {"version": ver, "sha256": sha})
        return ver
    except ValueError as e:
        db.set_build(mid, state="error", step="", error=str(e))
    except Exception:
        traceback.print_exc()
        db.set_build(mid, state="error", step="", error=ERR_GENERIC)
    return None
