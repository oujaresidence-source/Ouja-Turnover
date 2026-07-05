# -*- coding: utf-8 -*-
"""watchdog.engine — PURE deterministic logic (no I/O, stdlib only): code-send
classification, automation fingerprinting (the Aseel rule), flag computation, and the
phone-first Discord renderers. TDD-locked by tests/test_watchdog_engine.py."""

import hashlib
import re
