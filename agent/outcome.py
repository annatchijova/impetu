# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Anna Tchijova
"""Three-state outcomes for side effects, because two states are a lie.

A blanket `except Exception -> ok: False` collapses three genuinely different
worlds into one:

  DONE     the side effect happened and we know it
  FAILED   the side effect did not happen and we know it
  UNKNOWN  we lost the answer; the side effect may or may not exist

Reporting UNKNOWN as FAILED is a false negative, and the agent acts on it by
doing the thing again. `AGENTS.md` invariant 5 ("never fake success") only ever
guarded the false positive; this module guards the other direction.

Classification rule: a 4xx means the server processed the request and rejected
it, so nothing committed. A 5xx or any transport error may have arrived, been
applied, and lost its response. When in doubt we say UNKNOWN, never FAILED.
"""

from __future__ import annotations

DONE = "done"
FAILED = "failed"
UNKNOWN = "unknown"

_UNKNOWN_HINT = (
    "The request may have been applied before the answer was lost. Do NOT retry "
    "blind and do NOT tell the person it did not happen: say plainly that it is "
    "uncertain and offer to check."
)


def _status_of(exc: Exception):
    """Best-effort HTTP status from a googleapiclient error, or None."""
    resp = getattr(exc, "resp", None)
    status = getattr(resp, "status", None) or getattr(exc, "status_code", None)
    try:
        return int(status) if status is not None else None
    except (TypeError, ValueError):
        return None


def classify(exc: Exception) -> str:
    """FAILED only when the server demonstrably rejected the request."""
    status = _status_of(exc)
    if status is not None and 400 <= status < 500 and status not in (408, 429):
        return FAILED
    return UNKNOWN


def failure(exc: Exception, what: str) -> dict:
    """Build the honest result dict for a raised side-effect call."""
    state = classify(exc)
    out = {"ok": False, "status": state, "reason": f"{what}: {exc}"}
    if state == UNKNOWN:
        out["uncertain"] = True
        out["reason"] = f"{what} - outcome UNKNOWN: {exc}"
        out["guidance"] = _UNKNOWN_HINT
    return out
