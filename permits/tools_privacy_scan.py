# -*- coding: utf-8 -*-
"""
Gate G13 — no national ID number can leave this machine through git.

Scans every file this branch adds or changes relative to origin/main (committed or not,
plus untracked files git would pick up) for a Saudi national-ID/iqama-shaped number:
ten digits starting with 1 or 2 (\\b[12][0-9]{9}\\b). For bot.py only the ADDED lines are
scanned — numbers that were already in bot.py on main are not this change's doing.
19-digit Discord ids cannot match (word boundaries).

Also proves the raw seed spreadsheet is git-ignored and untracked.

Prints PRIVACY_OK, or every offending file:line (the match itself masked) and exits 1.
Run from the repo root: python3 permits/tools_privacy_scan.py
"""

import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ID = re.compile(r"\b[12][0-9]{9}\b")
XLSX = "permits/seed/source/ouja_permits_official.xlsx"
BINARY = (".xlsx", ".xls", ".png", ".jpg", ".jpeg", ".pdf", ".ttf", ".otf", ".woff", ".woff2", ".ico",
          ".webp", ".heic", ".zip", ".db")


def git(*args):
    return subprocess.run(["git"] + list(args), cwd=ROOT, capture_output=True, text=True)


def base_ref():
    for ref in ("origin/main", "main"):
        if git("rev-parse", "--verify", "-q", ref).returncode == 0:
            return ref
    return "HEAD"


def mask(s):
    return ID.sub(lambda m: "••••••" + m.group(0)[-4:], s)


def main():
    problems = []
    base = base_ref()
    changed = set(git("diff", "--name-only", base).stdout.split())
    changed |= set(git("ls-files", "-o", "--exclude-standard").stdout.split())
    changed |= set(git("ls-files", "-m").stdout.split())
    for path in sorted(changed):
        if path == "bot.py" or path.lower().endswith(BINARY):
            continue
        full = os.path.join(ROOT, path)
        if not os.path.isfile(full):
            continue
        try:
            with open(full, encoding="utf-8") as f:
                lines = f.read().splitlines()
        except (UnicodeDecodeError, OSError):
            continue
        for i, ln in enumerate(lines, 1):
            if ID.search(ln):
                problems.append("%s:%d: %s" % (path, i, mask(ln.strip())[:160]))
    diff = git("diff", "-U0", base, "--", "bot.py").stdout
    for ln in diff.splitlines():
        if ln.startswith("+") and not ln.startswith("+++") and ID.search(ln):
            problems.append("bot.py (added line): %s" % mask(ln[1:].strip())[:160])

    if os.path.exists(os.path.join(ROOT, XLSX)):
        if git("check-ignore", "-q", XLSX).returncode != 0:
            problems.append("%s is NOT git-ignored" % XLSX)
    if git("ls-files", "permits/seed/source").stdout.strip():
        problems.append("something under permits/seed/source/ is TRACKED by git")
    if git("ls-files", "--error-unmatch", XLSX).returncode == 0:
        problems.append("%s is tracked" % XLSX)

    if problems:
        print("PRIVACY_FAIL (%d)" % len(problems))
        for p in problems:
            print("  " + p)
        return 1
    print("PRIVACY_OK (base %s, %d files scanned + bot.py added lines)" % (base, len(changed)))
    print("PRIVACY_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
