# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Anna Tchijova
"""Root agent wiring: instruction + tools + model.

The model is configurable via env (MODEL), defaulting to a current Gemini. The
hackathon requires Gemini 3.5 or newer; set MODEL to the exact id from Vertex /
AI Studio at deploy time. LlmAgent.instruction may be a callable, which lets us
inject live state later; for now the static instruction carries the design.
"""

from __future__ import annotations

import os

from google.adk.agents import LlmAgent
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.models.google_llm import Gemini
from google.genai import types

from .prompts import SYSTEM_INSTRUCTION
from .tools import ALL_TOOLS, _store

MODEL = os.environ.get("MODEL", "gemini-3.5-flash")

# Gemini spikes to 503/429 under load; retry with exponential backoff so a
# transient overload degrades into a short wait, not a failed turn. Failure
# handling is a first-class concern here (hackathon Architecture criterion).
_model = Gemini(
    model=MODEL,
    retry_options=types.HttpRetryOptions(
        attempts=5,
        initial_delay=1.0,
        max_delay=20.0,
        exp_base=2.0,
        jitter=0.5,
        http_status_codes=[429, 500, 502, 503, 504],
    ),
)

_ADDR_KNOWN = (
    "addressed as {address} - make every gendered word agree with that; never use "
    "slash forms like 'bloqueado/a'."
)
_ADDR_UNKNOWN = (
    "you do not yet know how they want to be addressed. Use neutral phrasing, never "
    "slash forms; early and gently ask whether they use él, ella, or elle, and call "
    "set_address_preference when they tell you."
)


def _memory_block(recall: dict) -> str:
    """Render what ÍMPETU already remembers, so it greets the user from there."""
    notes = recall.get("notes") or {}
    lines = ["\n\n# What you already remember about THIS user"]

    address = notes.get("address")
    lines.append("- Address: " + (_ADDR_KNOWN.format(address=address) if address else _ADDR_UNKNOWN))

    last = recall.get("last_energy")
    if last:
        note = f" ({last.get('note')})" if last.get("note") else ""
        lines.append(f"- Last energy they reported: {last.get('level')}/5{note}")

    for t in (recall.get("open_tasks") or [])[:5]:
        undone = [s for s in (t.get("steps") or []) if not s.get("done")]
        nxt = f" -> next: {undone[-1]['text']}" if undone else ""
        lines.append(f"- Open thread you are holding: {t.get('title', 'untitled')}{nxt}")

    learned = {k: v for k, v in notes.items() if k != "address" and not k.startswith("draft:")}
    for v in list(learned.values())[:5]:
        lines.append(f"- Learned about them: {v}")

    if recall and not recall.get("durable", True):
        lines.append("- (Memory is in-process only right now; it will not survive a restart.)")

    lines.append("Greet them from here - pick up where they left off; do not make them re-explain.")
    return "\n".join(lines)


def _instruction(ctx: ReadonlyContext) -> str:
    """Inject this user's remembered context into the prompt on every turn."""
    try:
        uid = ctx.state.get("user_id")
        recall = _store.recall_context(uid) if uid else {}
    except Exception:  # noqa: BLE001 - personalization is best-effort, never fatal
        recall = {}
    return SYSTEM_INSTRUCTION + _memory_block(recall)


root_agent = LlmAgent(
    name="impetu",
    model=_model,
    description=(
        "A calm collaborative partner for autistic/ADHD minds that lowers the "
        "activation energy of starting: one atomic step at a time, negotiated not "
        "commanded, doing the scary first 10% for you."
    ),
    instruction=_instruction,
    tools=ALL_TOOLS,
)
