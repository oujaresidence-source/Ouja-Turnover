# -*- coding: utf-8 -*-
"""Gate G13: run the full suite and compare its failing ids with .unlazy-baseline.txt.

Prints NO_NEW_FAILURES ran=<n> when every failure/error already failed on the untouched
branch point; otherwise NEW_FAILURES and the ids (exit 1). Run from the repo root:
    python3 -m rrdesk.tools_compare_baseline
(Zero backslashes on purpose — the package-wide structure rule; regexes use classes.)
"""
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NL = chr(10)
_ID = re.compile(r"^(?:FAIL|ERROR): ([^ ]+ [(][^ ]+[)])", re.M)
_RAN = re.compile(r"^Ran ([0-9]+) tests", re.M)


def main():
    with open(os.path.join(ROOT, ".unlazy-baseline.txt"), encoding="utf-8") as f:
        known = set(_ID.findall(f.read()))
    out = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests",
                          "-p", "test_*.py"], cwd=ROOT, capture_output=True, text=True)
    text = (out.stdout or "") + NL + (out.stderr or "")
    ran = _RAN.search(text)
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
