# -*- coding: utf-8 -*-
"""
rrdesk.outbox — every Discord side effect of «طلبات سام» is a row first, an action second.

    enqueue(ref, kind, payload)     INSERT OR IGNORE by UNIQUE(ref): queueing twice is a no-op
    drain(exec_fn)                  claim → execute → done | backoff 1/5/15/60 min (6 tries)

Two bot copies overlap for a minute during every Railway redeploy. Both may queue the same
side effect (the ref makes that one row) and both may drain (the atomic claim gives each row to
exactly one of them). That is the whole double-post defence; nothing relies on in-memory flags.

Kinds (executed by rrdesk.bridge.execute):
    post    {channel_id, content, embeds, reply_to, buttons, mentions}  -> {message_ids}
    edit    {channel_id, message_id, content?, embeds?, buttons?}       -> {message_ids}
    delete  {channel_id, message_id}                                     -> {}
    react   {channel_id, message_id, emoji}                              -> {}
    dm      {did, text, buttons?}                                        -> {message_ids}
    room    {channel_name, content, buttons?}   (watchdog / HR rooms)    -> {message_ids}
    board   {channel_name, content, message_id?}  edit in place          -> {message_ids}
`payload["on_done"]` (optional) tells flow.delivered what to remember about the result.
"""

import asyncio
import functools
from concurrent.futures import ThreadPoolExecutor

from . import db

# Our OWN small pool (the checkout/flow.run_blocking lesson): asyncio.to_thread shares the
# default pool with every background job in bot.py, and right after a deploy Hostaway work can
# hold all of it — a translation queued behind that would arrive minutes late.
_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="rrdesk")


async def run_blocking(fn, *args, **kwargs):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_pool, functools.partial(fn, *args, **kwargs))


def enqueue(ref, kind, payload, at=None):
    return db.enqueue(ref, kind, payload, at)


_drain_lock = {}


def _lock():
    loop = asyncio.get_running_loop()
    lk = _drain_lock.get(id(loop))
    if lk is None:
        lk = _drain_lock[id(loop)] = asyncio.Lock()
    return lk


async def drain(exec_fn, on_done=None, limit=20, now_fn=None):
    """Execute what is due. exec_fn(kind, payload) is async and returns a result dict;
    on_done(row, result) is sync (it runs on the pool). Returns (done, failed)."""
    now_fn = now_fn or db.now
    done = failed = 0
    async with _lock():
        rows = await run_blocking(db.outbox_due, now_fn(), limit)
        for r in rows:
            if not await run_blocking(db.claim_outbox, r["id"], now_fn()):
                continue                       # the other bot copy has it
            try:
                result = await exec_fn(r["kind"], r["payload"]) or {}
            except Exception as e:
                failed += 1
                verdict = await run_blocking(db.fail_outbox, r["id"], "%s: %s" % (type(e).__name__, e),
                                             now_fn())
                await run_blocking(db.log, "outbox_" + verdict, None,
                                   r["payload"].get("channel_id"), None, None,
                                   {"ref": r["ref"], "kind": r["kind"], "error": str(e)[:300]})
                print("[rrdesk] outbox %s %s failed (%s): %s" % (r["kind"], r["ref"], verdict, e))
                continue
            await run_blocking(db.finish_outbox, r["id"], result, now_fn())
            done += 1
            if on_done is not None:
                try:
                    await run_blocking(on_done, r, result)
                except Exception as e:
                    print("[rrdesk] outbox on_done failed (%s): %s" % (r["ref"], e))
    return done, failed
