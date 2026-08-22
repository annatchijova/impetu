# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Anna Tchijova
"""Production server for Cloud Run: the ÍMPETU agent + a proactive /nudge endpoint.

`get_fast_api_app` serves the agent and its web chat UI. We add `/nudge` so a Cloud
Scheduler job can trigger a proactive check-in on a cadence - ÍMPETU reaching out
first, instead of only answering when spoken to.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import Header, HTTPException
from fastapi.responses import HTMLResponse
from google.adk.cli.fast_api import get_fast_api_app
from starlette.routing import Route

from agent import nudge as nudge_mod

AGENTS_DIR = str(Path(__file__).resolve().parent.parent)
TZ = os.environ.get("IMPETU_TZ", "America/Argentina/Buenos_Aires")

app = get_fast_api_app(
    agents_dir=AGENTS_DIR,
    web=True,
    host="0.0.0.0",
    port=int(os.environ.get("PORT", "8080")),
)

# The product landing page (docs/impetu.html) — what ÍMPETU is, the proactive
# loop, the demo path, and a CTA into the agent — served at "/". get_fast_api_app
# registers a redirect from "/" straight to the raw agent chat (/dev-ui/), which
# is why a visitor "only saw the agent"; inserting our route at the front of the
# router makes the landing win while the agent stays at /dev-ui/. Non-destructive:
# the ADK redirect route stays in place, just shadowed.
_LANDING_HTML = (Path(__file__).resolve().parent.parent / "docs" / "impetu.html").read_text(encoding="utf-8")


async def _landing(_request) -> HTMLResponse:
    return HTMLResponse(_LANDING_HTML)


app.router.routes.insert(0, Route("/", _landing, methods=["GET"]))


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


_DEMO_USER = "demo"


@app.get("/api/state")
def api_state() -> dict:
    """Read-only snapshot for the landing's live action center.

    It always reads the fixed DEMO profile, never a real user, so the public
    page can surface real state (a real Firestore read, the real proactive
    move) without leaking anyone's tasks. Degrades honestly: `durable` says
    whether Firestore actually answered.
    """
    ctx = nudge_mod._store.recall_context(_DEMO_USER)
    open_tasks = ctx.get("open_tasks") or []
    current = open_tasks[0] if open_tasks else None
    next_step = None
    if current:
        undone = [s for s in (current.get("steps") or []) if not s.get("done")]
        next_step = undone[-1]["text"] if undone else None
    preview = nudge_mod.build_nudge(_DEMO_USER)
    energy = ctx.get("last_energy")
    return {
        "durable": ctx.get("durable"),
        "open_task_count": len(open_tasks),
        "current_task": ({"title": current.get("title"), "next_step": next_step}
                         if current else None),
        "last_energy": (energy.get("level") if energy else None),
        "nudge_preview": ({"title": preview["title"], "body": preview["body"]}
                          if preview else None),
    }


@app.post("/nudge")
def run_nudge(user_id: str = "user", x_nudge_token: Optional[str] = Header(default=None)) -> dict:
    """Proactive check-in for Cloud Scheduler: place a calendar reminder from open tasks.

    Protected by a shared secret (NUDGE_TOKEN) so only the scheduler can trigger it.
    """
    expected = os.environ.get("NUDGE_TOKEN")
    if expected and x_nudge_token != expected:
        raise HTTPException(status_code=403, detail="forbidden")
    when = (datetime.now(ZoneInfo(TZ)) + timedelta(minutes=1)).replace(microsecond=0).isoformat()
    return nudge_mod.place_nudge(user_id, when)
