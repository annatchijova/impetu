# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Anna Tchijova
"""The agent's hands: real actions that lower activation energy.

These are plain Python functions; ADK exposes them to the model as tools. Each one
either persists the externalized working memory or takes a concrete action (like
producing a real draft). Every return value carries a `persisted` flag so the agent
can be honest about whether something actually survived.

The user id comes from the session (set at session creation), never from the model,
so the model cannot read or write another person's state.
"""

from __future__ import annotations

from typing import Optional

from google.adk.tools import ToolContext

from . import gcal, gmail
from .state import Store

# One store per process. Firestore client is cheap to hold; falls back honestly.
_store = Store()


def _user_id(tool_context: ToolContext) -> str:
    # Prefer an explicit state value (our own server may set one), then fall back to
    # the ADK session's user id, which every runner - including `adk web` - populates.
    # Never invent an identity: that would mix different people's state.
    uid = tool_context.state.get("user_id")
    if uid:
        return uid
    session = getattr(tool_context, "session", None)
    uid = getattr(session, "user_id", None) if session is not None else None
    if uid:
        return uid
    raise ValueError("No user id on the tool context; session was not initialized.")


def recall_context(tool_context: ToolContext) -> dict:
    """Recall where this person was and how they felt, before saying anything.

    Call this first at the start of a conversation so you can greet them from where
    they actually left off - their open tasks, the last energy they reported, and
    anything you learned works for them.
    """
    ctx = _store.recall_context(_user_id(tool_context))
    if not ctx["durable"]:
        ctx["_warning"] = "Memory is in-process only right now; it will not survive a restart."
    return ctx


def save_task(title: str, raw_dump: str, tool_context: ToolContext) -> dict:
    """Save one overwhelming thing so it lives in you, not in their head.

    Args:
        title: a short, plain name for the thing (their words, not jargon).
        raw_dump: whatever they brain-dumped about it, verbatim, so nothing is lost.
    """
    res = _store.save_task(_user_id(tool_context), title, raw_dump)
    return {"task_id": res.data["task_id"], "persisted": res.persisted, "warning": res.warning}


def save_next_step(task_id: str, step_text: str, size: str, tool_context: ToolContext) -> dict:
    """Persist the ONE atomic next step you negotiated with them.

    Args:
        task_id: the task this step belongs to.
        step_text: the single, tiny, concrete next action (e.g. "open the doc").
        size: your read of how big it is - "tiny", "small", or "medium". If they
            hesitated, it should be "tiny"; if it still feels big, split it first.
    """
    res = _store.save_next_step(_user_id(tool_context), task_id, step_text, size)
    return {"step": res.data, "persisted": res.persisted, "warning": res.warning}


def mark_step_done(task_id: str, step_id: str, tool_context: ToolContext) -> dict:
    """Mark a step finished the moment they do it - then celebrate it, small as it is."""
    res = _store.mark_step_done(_user_id(tool_context), task_id, step_id)
    return {"ok": res.ok, "persisted": res.persisted, "warning": res.warning}


def log_energy(level: int, note: str, tool_context: ToolContext) -> dict:
    """Record the energy they reported (1 = empty, 5 = full) so you can adapt over time.

    Args:
        level: integer 1 to 5.
        note: optional short context ("didn't sleep", "post-meltdown"), or "".
    """
    level = max(1, min(5, int(level)))
    res = _store.log_energy(_user_id(tool_context), level, note or "")
    return {"logged": level, "persisted": res.persisted, "warning": res.warning}


def remember(key: str, value: str, tool_context: ToolContext) -> dict:
    """Remember something durable about THIS person (a preference, a pattern, a win).

    Use for things that should shape every future session: "mornings are low energy",
    "responds well to silly-small steps", "hates phone calls". This is how you get
    more attuned to them over time.
    """
    res = _store.remember(_user_id(tool_context), key, value)
    return {"remembered": key, "persisted": res.persisted, "warning": res.warning}


def note_what_worked(observation: str, tool_context: ToolContext) -> dict:
    """Record a framing or step-size that clearly landed, to reuse it next time."""
    res = _store.remember(_user_id(tool_context), f"worked:{observation[:40]}", observation)
    return {"noted": True, "persisted": res.persisted, "warning": res.warning}


def set_address_preference(pronoun: str, tool_context: ToolContext) -> dict:
    """Remember how this person wants to be addressed, so grammar always agrees.

    Call this as soon as they tell you (or you can safely infer it from how they
    refer to themselves). This is durable and shapes every future session - it is
    how you stop using clumsy slash forms like "bloqueado/a" and address them the
    way they actually are.

    Args:
        pronoun: their stated preference, e.g. "él", "ella", or "elle" (or their
            own words if different). Store it verbatim.
    """
    res = _store.remember(_user_id(tool_context), "address", pronoun.strip())
    return {"address": pronoun.strip(), "persisted": res.persisted, "warning": res.warning}


def draft_email(to: str, subject: str, body: str, tool_context: ToolContext) -> dict:
    """Do the scary 10%: produce a real email draft they can just edit and send.

    You compose `body` in their voice - warm-but-brief, honest, no corporate padding.
    This stores the draft and, when Gmail is connected, creates a real draft in their
    Gmail so opening it is one click, not a blank page. It never sends - they always
    press send. If Gmail is not connected, `gmail_draft_created` comes back False with a
    reason; tell them honestly and offer the draft text so they can paste it themselves.

    Args:
        to: recipient (email or a plain description if unknown, e.g. "my landlord").
        subject: a plain subject line.
        body: the full draft text, ready to edit.
    """
    uid = _user_id(tool_context)
    # Persist the draft as an artifact of the task work, regardless of Gmail state.
    res = _store.remember(uid, f"draft:{subject[:40]}", f"TO: {to}\nSUBJECT: {subject}\n\n{body}")
    # Create a real Gmail draft when connected; degrade honestly when not.
    gmail_result = gmail.create_draft(to, subject, body)
    return {
        "draft": {"to": to, "subject": subject, "body": body},
        "gmail_draft_created": gmail_result.get("created", False),
        "gmail_draft_id": gmail_result.get("draft_id"),
        "gmail_reason": gmail_result.get("reason"),
        "persisted": res.persisted,
        "warning": res.warning,
    }


def get_today_schedule() -> dict:
    """Read what the person already has on their calendar today.

    Use this to gauge what is realistic before proposing scope - if the day is already
    full, offer a smaller move or explicit permission to not add more. Returns the
    events (or an honest reason if Calendar is not connected yet).
    """
    return gcal.list_today()


def schedule_reminder(summary: str, when_iso: str, note: str) -> dict:
    """Place a gentle reminder on their calendar - ONLY after they agreed to a time.

    This is a normal calendar event, never a nag. Do not schedule anything they did not
    explicitly ask for.

    Args:
        summary: short title of the reminder (their words).
        when_iso: ISO 8601 start time, e.g. "2026-08-20T16:00:00".
        note: optional extra context, or "".
    """
    return gcal.create_event(summary, when_iso, description=note or "")


def search_email(query: str) -> dict:
    """Search the person's own Gmail to find a fact they asked about.

    Use this when they need something that lives in their inbox - "what was that
    address", "when did they say the appointment was", "what did the bank ask for".
    Search only for what they actually asked; this is read-only and never sends,
    deletes, or changes anything. Summarize what you find; do not dump whole emails.

    Args:
        query: a Gmail search query, e.g. "Defensoria", "from:banco turno", "monotributo".
    """
    return gmail.search_messages(query, max_results=5)


def read_email(message_id: str) -> dict:
    """Read the full text of one email (by id from search_email) when a snippet is not enough."""
    return gmail.get_message(message_id)


# The ordered toolset handed to the agent.
ALL_TOOLS = [
    recall_context,
    save_task,
    save_next_step,
    mark_step_done,
    log_energy,
    remember,
    note_what_worked,
    set_address_preference,
    draft_email,
    search_email,
    read_email,
    get_today_schedule,
    schedule_reminder,
]
