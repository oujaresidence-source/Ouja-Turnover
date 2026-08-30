# PLAN — Owners / المركز المالي performance

Branch: `perf/owners-fast`, based on `origin/main` (`ebe8d34`).
Worktree: `/Users/faisalouja/ouja-wt-ownerperf` (main checkout stays on `feat/musaed-v2`, untouched).

## Base correction — recorded before the first edit

The brief's line numbers, file sizes, loop count and test count match `origin/main` exactly
(bot.py 70,129 lines · 212 test files · 52 `@tasks.loop` · erp.js 395 KB). They do NOT match
the local checkout, which sits on `feat/musaed-v2` and whose local `main` is **169 commits
behind `origin/main`**. All work is therefore based on `origin/main`, in a worktree.

Runtime split: Railway pins `.python-version` = **3.13.13**; local `python3` is **3.9.6**.
All new code must parse and run on **both** → no PEP 604 (`X | None`) annotations, no
`match`, nothing newer than 3.9. Local verification is only meaningful under that rule.

## Baseline, measured on untouched `origin/main`

```
Ran 3699 tests in 43.669s
FAILED (failures=2, skipped=1)
FAIL: test_an_unlinked_apartment_is_counted_as_unattributed (test_ops_capture.TestBackfill)
FAIL: test_it_reports_how_much_it_could_attribute (test_ops_capture.TestBackfill)
```

Both failures are **pre-existing and date-expired**: `tests/test_ops_capture.py:34` hardcodes
`TUE = date(2026, 7, 28)`, today is 2026-08-30, so the backfill's rolling window is empty
(`events_in_window` 0 != 2). Unrelated to owners/finance, and out of scope per §8.

**G2 is therefore restated**: the gate is *no NEW failures* — same 3,699 tests, same 2
pre-existing failures, nothing added. "All 212 files pass" is already false on untouched
main and cannot be a gate.

## Gates

G1 — Numbers unchanged. Statement JSON for a real owner-month is byte-identical pre/post.
    CHECK: python3 tools/perf_g1_snapshot.py --compare
    EXPECT: G1-IDENTICAL

G2 — No new test failures (see restatement above).
    CHECK: python3 -m unittest discover -s tests -p "test_*.py" 2>&1 | tail -3
    EXPECT: failures=2

G3 — Syntax gates, all four.
    CHECK: python3 -W error::SyntaxWarning -m py_compile bot.py && python3 -m pyflakes bot.py finance/*.py | grep -v "imported but unused" ; node --check finance/static/erp.js && python3 tools/perf_g3_esprima.py
    EXPECT: G3-ALL-CLEAN

G4 — Cold profile ≤ 10 Hostaway calls, same nets.
    CHECK: python3 -m unittest tests.test_owner_perf_budget -v 2>&1 | tail -3
    EXPECT: OK

G5 — Warm profile = 0 Hostaway calls. (same test module)
G6 — Single-flight: 5 concurrent identical computes → exactly 1 underlying compute.
G7 — Wall clock: p95 of 20 warm profile loads < 1.5 s; 20 warm statement loads < 1.0 s.
G8 — Invalidation exact: edit / publish / contract change each visible on the next read.
G9 — Degradation honest: page-1 failure still sets `degraded`, still refuses publish.
G10 — erp.js served gzip, < 90 KB, `Cache-Control: immutable`.
G11 — The two screenshot URLs render (no dead skeleton, no «تعذّر تحميل البيانات»).

## Rules I am holding myself to

- Numbers before speed. G1 is the veto gate: if statement totals move by one halala, the
  whole branch is wrong regardless of how fast it got.
- Re-read surrounding code before each edit (CLAUDE.md trap #5). No editing from memory.
- G2 + G3 after **every** commit, not only at the end.
- If a gate cannot be met: do not push, leave the branch, say so plainly at the top of the report.
