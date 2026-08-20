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


def place_nudge(user_id: str, when_iso: str) -> dict:
    """Turn the next open task into an active calendar reminder at `when_iso`."""
    nudge = build_nudge(user_id)
    if nudge is None:
        return {"ok": False, "reason": "No open tasks to nudge about - nothing to push."}
    result = gcal.create_event(nudge["title"], when_iso, description=nudge["body"])
    return {"ok": result.get("ok"), "nudge": nudge, "calendar": result}
