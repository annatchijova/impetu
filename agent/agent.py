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

from .prompts import SYSTEM_INSTRUCTION
from .tools import ALL_TOOLS, _store

MODEL = os.environ.get("MODEL", "gemini-3.5-flash")

_KNOWN = (
    "\n\n# Personalization (THIS user)\n"
    "They are addressed as: {address}. Make every gendered word agree with that. "
    "Never use slash forms like 'bloqueado/a' - you know how they are addressed."
)
_UNKNOWN = (
    "\n\n# Personalization (THIS user)\n"
    "You do not yet know how they want to be addressed. Until you do, use neutral "
    "phrasing and never slash forms like 'bloqueado/a'. Early and gently, ask "
    "whether they use él, ella, or elle; when they say, call set_address_preference."
)


def _instruction(ctx: ReadonlyContext) -> str:
    """Inject the user's stored address preference into the prompt each turn."""
    address = None
    try:
        uid = ctx.state.get("user_id")
        if uid:
            address = _store.recall_context(uid).get("notes", {}).get("address")
    except Exception:  # noqa: BLE001 - personalization is best-effort, never fatal
        address = None
    return SYSTEM_INSTRUCTION + (_KNOWN.format(address=address) if address else _UNKNOWN)


root_agent = LlmAgent(
    name="impetu",
    model=MODEL,
    description=(
        "A calm collaborative partner for autistic/ADHD minds that lowers the "
        "activation energy of starting: one atomic step at a time, negotiated not "
        "commanded, doing the scary first 10% for you."
    ),
    instruction=_instruction,
    tools=ALL_TOOLS,
)
