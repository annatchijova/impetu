# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Anna Tchijova
"""Go back and find out what actually happened.

An UNKNOWN outcome (see `agent/outcome.py`) means the side effect may or may not
exist. Recording it was the first half of the fix; this is the second. Because
`state.record_side_effect` now persists the identity of everything ÍMPETU creates
outside itself, we can ask Google directly instead of guessing - which is what
turns "I am not sure" into an answer rather than a permanent shrug.

Deliberately NOT automatic-everywhere: it runs before the proactive nudge (so the
scheduled loop self-heals) and when the agent is asked, not on every turn.
"""

from __future__ import annotations

from . import gcal, gmail, outcome

# A draft we never got an id for is matched by subject, which cannot distinguish
# two drafts with the same subject. Resolutions from that path say so.
PENDING_PREFIX = "pending-"


def reconcile_pending(store, user_id: str, limit: int = 10) -> dict:
    """Resolve UNKNOWN side effects against Google. Returns a small summary."""
    pending = store.pending_side_effects(user_id)[:limit]
    resolved, still_unknown = [], 0

    for item in pending:
        external_id = item.get("external_id", "")
        kind = item.get("kind")

        if kind == "calendar_event" and not external_id.startswith(PENDING_PREFIX):
            look = gcal.get_event(external_id, user_id=user_id)
        elif kind == "gmail_draft":
            look = gmail.find_draft_by_subject(item.get("detail", ""), user_id=user_id)
        else:
            still_unknown += 1
            continue

        if not look.get("ok"):
            still_unknown += 1
            continue

        exists = bool(look.get("exists"))
        status = outcome.DONE if exists else outcome.FAILED
        store.resolve_side_effect(user_id, external_id, status,
                                  resolved_id=look.get("draft_id", ""))
        store.log_activity(
            user_id, "reconcile",
            f"Confirmed an uncertain {kind.replace('_', ' ')}: "
            f"{'it exists' if exists else 'it never happened'}",
            status=status)
        resolved.append({"kind": kind, "detail": item.get("detail", ""),
                         "exists": exists})

    return {"checked": len(pending), "resolved": resolved,
            "still_unknown": still_unknown}
