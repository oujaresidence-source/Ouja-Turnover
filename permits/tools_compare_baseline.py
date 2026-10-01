# -*- coding: utf-8 -*-
"""Gate G4: run the full suite and compare its failing test ids against permits/.baseline.txt.

Prints NO_NEW_FAILURES ran=<n> when every failure/error is one that already failed on the
untouched main branch; otherwise prints NEW_FAILURES and the new ids (and exits 1).
Run from the repo root: python3 permits/tools_compare_baseline.py
"""
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ID = re.compile(r"^(?:FAIL|ERROR): (\S+ \(\S+\))", re.M)


def main():
    with open(os.path.join(ROOT, "permits", ".baseline.txt"), encoding="utf-8") as f:
        known = set(_ID.findall(f.read()))
    out = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests",
                          "-p", "test_*.py"], cwd=ROOT, capture_output=True, text=True)
    text = (out.stdout or "") + "\n" + (out.stderr or "")
    ran = re.search(r"^Ran (\d+) tests", text, re.M)
    if not ran:
        print("SUITE_DID_NOT_RUN")
        print(text[-3000:])
        return 1
    bad = set(_ID.findall(text))
    new = sorted(bad - known)
    if new:
        print("NEW_FAILURES ran=%s" % ran.group(1))
        for n in new:
            print("  " + n)
        return 1
    print("NO_NEW_FAILURES ran=%s (pre-existing: %d)" % (ran.group(1), len(bad & known)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
