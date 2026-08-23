# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Anna Tchijova
"""Proactive nudges: ÍMPETU reaches out first, instead of waiting to be asked.

A passive assistant only answers when spoken to; for an ADHD brain that is not
enough. This turns an open task into an active reminder that comes to the person.

`build_nudge` composes a short check-in from the person's open tasks (no LLM needed,
so it is cheap and safe to run on a schedule). `place_nudge` drops it on the calendar
as a notifying reminder. On deploy, a Cloud Scheduler job calls this on a cadence; the
same function is testable now by calling it directly.
"""

from __future__ import annotations

from typing import Optional

from . import gcal
from .state import Store

_store = Store()


def build_nudge(user_id: str) -> Optional[dict]:
    """Compose a check-in from the person's open tasks, or None if nothing is open."""
    ctx = _store.recall_context(user_id)
    open_tasks = ctx.get("open_tasks") or []
    if not open_tasks:
        return None
    task = open_tasks[0]
    undone = [s for s in (task.get("steps") or []) if not s.get("done")]
    step = undone[-1]["text"] if undone else None
    title = f"ÍMPETU: ¿seguimos con {task.get('title', 'eso')}?"
    body = f"El paso que dejamos: {step}" if step else "¿Buscamos juntas el próximo paso chico?"
    return {"title": title, "body": body, "task_id": task.get("task_id")}


def place_nudge(user_id: str, when_iso: str, day_key: str = "") -> dict:
    """Turn the next open task into an active calendar reminder at `when_iso`.

    The reminder is keyed to the LOGICAL operation - this person, this task, this
    day - not to the moment of invocation. A duplicated scheduler firing, a retry
    after a lost response, or a manual re-run therefore converge on one event
    instead of stacking reminders. See docs/RED-TEAM.md F4.
    """
    nudge = build_nudge(user_id)
    if nudge is None:
        return {"ok": False, "reason": "No open tasks to nudge about - nothing to push."}
    day = day_key or when_iso[:10]
    key = f"nudge|{user_id}|{nudge.get('task_id') or nudge['title']}|{day}"
    result = gcal.create_event(nudge["title"], when_iso, description=nudge["body"],
                               idempotency_key=key)
    # Record what we created out in the world, so a later run can tell whether
    # this already happened instead of guessing. See docs/RED-TEAM.md F9.
    _store.record_side_effect(user_id, "calendar_event", result.get("event_id", ""),
                              result.get("status", "unknown"), nudge["title"])
    _store.log_activity(user_id, "nudge",
                        f"Placed reminder: {nudge['title']}",
                        status=result.get("status", "unknown"))
    return {"ok": result.get("ok"), "status": result.get("status"),
            "duplicate": result.get("duplicate", False),
            "nudge": nudge, "calendar": result}
