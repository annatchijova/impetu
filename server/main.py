# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Anna Tchijova
"""Production server for Cloud Run: the ÍMPETU agent + a proactive /nudge endpoint.

`get_fast_api_app` serves the agent and its web chat UI. We add `/nudge` so a Cloud
Scheduler job can trigger a proactive check-in on a cadence - ÍMPETU reaching out
first, instead of only answering when spoken to.
"""

from __future__ import annotations

import hmac
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import Header, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from google.adk.cli.fast_api import get_fast_api_app
from starlette.routing import Route

from agent import nudge as nudge_mod
from agent.identity import ENV_OWNER, owner_user_id

log = logging.getLogger("impetu.server")

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


_DEMO_USER = "demo"

# The ADK routes carry `user_id` as a path segment and have no auth of their own,
# so with `--allow-unauthenticated` anyone could open a session as anyone and read
# that person's tasks, notes and drafts. Fail closed: either present a token, or
# run explicitly as the public demo (which is pinned to the demo profile).
# See docs/RED-TEAM.md F1.
_GATED_PREFIXES = ("/apps/", "/dev/", "/dev-ui", "/run", "/list-apps", "/builder")
_ACCESS_TOKEN = os.environ.get("IMPETU_ACCESS_TOKEN", "").strip()
_PUBLIC_DEMO = os.environ.get("IMPETU_PUBLIC_DEMO", "").strip() == "1"

if not _ACCESS_TOKEN and not _PUBLIC_DEMO:
    log.warning("Neither IMPETU_ACCESS_TOKEN nor IMPETU_PUBLIC_DEMO=1 is set; the "
                "agent routes are closed. Set one of them deliberately.")
if not owner_user_id():
    log.warning("%s is not set; Gmail and Calendar actions are disabled because the "
                "deployment cannot prove whose token is connected.", ENV_OWNER)


def _path_user_id(path: str) -> Optional[str]:
    parts = [p for p in path.split("/") if p]
    if len(parts) >= 3 and parts[0] == "apps" and parts[2] == "users":
        return parts[3] if len(parts) >= 4 else None
    return None


@app.middleware("http")
async def _gate_agent_routes(request, call_next):
    path = request.url.path
    if not path.startswith(_GATED_PREFIXES):
        return await call_next(request)

    if _ACCESS_TOKEN:
        presented = (request.headers.get("x-impetu-token")
                     or request.headers.get("authorization", "").removeprefix("Bearer ").strip())
        if hmac.compare_digest(presented, _ACCESS_TOKEN):
            return await call_next(request)
        return JSONResponse({"detail": "forbidden"}, status_code=403)

    if _PUBLIC_DEMO:
        uid = _path_user_id(path)
        if uid is not None and uid != _DEMO_USER:
            return JSONResponse(
                {"detail": f"This deployment is a public demo: only user_id "
                           f"'{_DEMO_USER}' is available."}, status_code=403)
        return await call_next(request)

    return JSONResponse(
        {"detail": "Agent routes are disabled. Set IMPETU_ACCESS_TOKEN (private) or "
                   "IMPETU_PUBLIC_DEMO=1 (demo profile only)."}, status_code=503)


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


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
    activity = nudge_mod._store.recent_activity(_DEMO_USER, 6)
    return {
        "durable": ctx.get("durable"),
        "open_task_count": len(open_tasks),
        "current_task": ({"title": current.get("title"), "next_step": next_step}
                         if current else None),
        "last_energy": (energy.get("level") if energy else None),
        "nudge_preview": ({"title": preview["title"], "body": preview["body"]}
                          if preview else None),
        "activity": [{"kind": a.get("kind"), "summary": a.get("summary"),
                      "at": a.get("at")} for a in activity],
    }


@app.post("/nudge")
def run_nudge(user_id: str = "", x_nudge_token: Optional[str] = Header(default=None)) -> dict:
    """Proactive check-in for Cloud Scheduler: place a calendar reminder from open tasks.

    Two separate checks, because they answer two different questions:

      1. NUDGE_TOKEN authenticates the CALLER as the scheduler. It is required -
         an unset token used to skip the check entirely and let anyone in
         (docs/RED-TEAM.md F3).
      2. IMPETU_OWNER_USER_ID authorizes the OBJECT. Holding the scheduler secret
         never meant permission to operate on a named person, and the reminder
         lands on the shared token owner's calendar regardless of which user_id
         was asked for - so a mismatch leaked one person's tasks into another
         person's calendar and inbox (docs/RED-TEAM.md F2).
    """
    expected = (os.environ.get("NUDGE_TOKEN") or "").strip()
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="NUDGE_TOKEN is not configured; the proactive endpoint is closed.")
    if not hmac.compare_digest(x_nudge_token or "", expected):
        raise HTTPException(status_code=403, detail="forbidden")

    owner = owner_user_id()
    if not owner:
        raise HTTPException(
            status_code=503,
            detail=f"{ENV_OWNER} is not configured; refusing to place a reminder when "
                   "the account it would land on cannot be established.")
    target = (user_id or owner).strip()
    if target != owner:
        raise HTTPException(
            status_code=403,
            detail="This endpoint can only nudge the account that owns the connected "
                   "Google token.")

    now = datetime.now(ZoneInfo(TZ))
    when = (now + timedelta(minutes=1)).replace(microsecond=0).isoformat()
    # Key the reminder to the day, not the instant: a duplicated firing or a retry
    # then converges on one event. See docs/RED-TEAM.md F4.
    return nudge_mod.place_nudge(target, when, day_key=now.date().isoformat())
