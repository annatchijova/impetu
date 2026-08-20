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

from .state import Store

# One store per process. Firestore client is cheap to hold; falls back honestly.
_store = Store()


def _user_id(tool_context: ToolContext) -> str:
    uid = tool_context.state.get("user_id")
    if not uid:
        # Never silently invent an identity - that would mix people's state.
        raise ValueError("No user_id in session state; session was not initialized.")
    return uid


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
    This stores the draft and (in production) creates it in their Gmail so opening it
    is one click, not a blank page. Never send automatically; they always press send.

    Args:
        to: recipient (email or a plain description if unknown, e.g. "my landlord").
        subject: a plain subject line.
        body: the full draft text, ready to edit.
    """
    uid = _user_id(tool_context)
    # Persist the draft as an artifact of the task work.
    res = _store.remember(uid, f"draft:{subject[:40]}", f"TO: {to}\nSUBJECT: {subject}\n\n{body}")
    # TODO(gmail): create a real Gmail draft via the Gmail API / connected MCP so it
    # lands in their drafts folder. Kept as a hook so the scaffold runs without creds.
    gmail_created = False
    return {
        "draft": {"to": to, "subject": subject, "body": body},
        "gmail_draft_created": gmail_created,
        "persisted": res.persisted,
        "warning": res.warning,
    }


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
]
