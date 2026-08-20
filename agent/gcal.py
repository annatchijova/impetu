# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Anna Tchijova
"""Google Calendar: read the day, place a gentle reminder.

Reading the day lets ÍMPETU gauge what is realistic before proposing scope ("you
already have three things today"). A reminder is a normal calendar event the user
agreed to - never a nag, always opt-in. Degrades honestly if Calendar is not
authorized yet (the token may only have the Gmail scope until re-consent).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from .google_auth import load_creds

DEFAULT_TZ = "America/Argentina/Buenos_Aires"


def _service():
    creds = load_creds()
    if creds is None:
        return None
    from googleapiclient.discovery import build

    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def list_today(tz: str = DEFAULT_TZ) -> dict:
    """Return today's events (summary + start), or an honest reason if unavailable."""
    svc = _service()
    if svc is None:
        return {"ok": False, "reason": "Calendar not connected - re-authorize to add the Calendar scope."}
    try:
        from zoneinfo import ZoneInfo

        now = datetime.now(ZoneInfo(tz))
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        items = (
            svc.events()
            .list(
                calendarId="primary",
                timeMin=start.isoformat(),
                timeMax=end.isoformat(),
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
            .get("items", [])
        )
        events = [
            {
                "summary": e.get("summary", "(sin título)"),
                "start": e.get("start", {}).get("dateTime") or e.get("start", {}).get("date"),
            }
            for e in items
        ]
        return {"ok": True, "count": len(events), "events": events}
    except Exception as exc:  # noqa: BLE001 - report honestly, never crash a turn
        return {"ok": False, "reason": f"Calendar error (is the Calendar scope authorized?): {exc}"}


def create_event(summary: str, start_iso: str, end_iso: str = "", description: str = "",
                 tz: str = DEFAULT_TZ) -> dict:
    """Create a calendar event (a reminder the user approved). Returns id + link, or a reason."""
    svc = _service()
    if svc is None:
        return {"ok": False, "reason": "Calendar not connected - re-authorize to add the Calendar scope."}
    try:
        if not end_iso:
            end_iso = (datetime.fromisoformat(start_iso) + timedelta(minutes=30)).isoformat()
        body = {
            "summary": summary,
            "description": description,
            "start": {"dateTime": start_iso, "timeZone": tz},
            "end": {"dateTime": end_iso, "timeZone": tz},
        }
        ev = svc.events().insert(calendarId="primary", body=body).execute()
        return {"ok": True, "event_id": ev.get("id"), "link": ev.get("htmlLink")}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "reason": f"Calendar error: {exc}"}
