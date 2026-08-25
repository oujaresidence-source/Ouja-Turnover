# -*- coding: utf-8 -*-
"""Shared exception types for the owner_report pipeline.

Every failure mode in this module is a hard stop. There are no silent fallbacks:
if a value is missing, untagged, unconfirmed, or fails a gate, the report does not
render. These exceptions carry an operator-facing bilingual message where possible.
"""


class BuildError(RuntimeError):
    """A report could not be produced. Fatal; the PDF is never emitted."""


class ValidationError(BuildError):
    """One or more hard gates failed. Carries the list of violations."""

    def __init__(self, violations):
        self.violations = list(violations)
        super().__init__(
            "Report blocked by "
            + str(len(self.violations))
            + " hard-gate violation(s):\n  - "
            + "\n  - ".join(str(v) for v in self.violations)
        )
