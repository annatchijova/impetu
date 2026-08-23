# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Anna Tchijova
"""Google Calendar: read the day, place a gentle reminder.

Reading the day lets ÍMPETU gauge what is realistic before proposing scope ("you
already have three things today"). A reminder is a normal calendar event the user
agreed to - never a nag, always opt-in. Degrades honestly if Calendar is not
authorized yet (the token may only have the Gmail scope until re-consent).
"""

from __future__ import annotations

import base64
import hashlib
import re
from datetime import datetime, timedelta

from . import outcome
from .google_auth import load_creds

DEFAULT_TZ = "America/Argentina/Buenos_Aires"

# Google caps these well above what a reminder needs; we cap far lower so a
# single stored string cannot dominate a notification.
MAX_SUMMARY = 300
MAX_DESCRIPTION = 1000

# Anything that is not printable text has no business in a calendar reminder.
# This is the last point where untrusted durable state (a task title someone
# else may have written) can be neutralised before it leaves for Google and
# comes back as a notification email. See docs/RED-TEAM.md F8.
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f\u200b-\u200f\u202a-\u202e\u2066-\u2069]")


def sanitize_text(value: str, limit: int) -> str:
    """Strip control/bidi characters, collapse newlines, and cap the length."""
    text = _CONTROL.sub("", value or "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "\n".join(line.strip() for line in text.split("\n"))
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "\u2026"
    return text


def event_id_for(idempotency_key: str) -> str:
    """Deterministic Calendar event id for one logical operation.

    Calendar accepts a client-supplied id using the base32hex alphabet (a-v,
    0-9). Deriving it from the LOGICAL operation - the user and the task - rather
    than from the wall clock is what makes a retry converge instead of
    duplicating: a second insert with the same id comes back 409, which is the
    success case, not an error. See docs/RED-TEAM.md F4.
    """
    digest = hashlib.sha256(idempotency_key.encode("utf-8")).digest()
    encoded = base64.b32hexencode(digest).decode("ascii").lower().rstrip("=")
    return f"impetu{encoded[:26]}"


def _service():
    creds = load_creds()
    if creds is None:
        return None
    from googleapiclient.discovery import build

    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def _is_conflict(exc: Exception) -> bool:
    """True when Calendar rejected an insert because that event id already exists."""
    status = getattr(getattr(exc, "resp", None), "status", None)
    return status == 409 or "409" in str(exc)


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
        return outcome.failure(exc, "Calendar error (is the Calendar scope authorized?)")


def get_event(event_id: str) -> dict:
    """Does this event exist on the calendar right now?

    Used to resolve an UNKNOWN outcome: we know the id we asked Calendar to use,
    so we can go back and ask instead of guessing. Returns
    `{ok, exists}`; `ok=False` means we still could not find out.
    See docs/RED-TEAM.md F5.
    """
    svc = _service()
    if svc is None:
        return {"ok": False, "reason": "Calendar not connected."}
    try:
        ev = svc.events().get(calendarId="primary", eventId=event_id).execute()
        # A deleted event still resolves, with status "cancelled".
        return {"ok": True, "exists": ev.get("status") != "cancelled",
                "link": ev.get("htmlLink")}
    except Exception as exc:  # noqa: BLE001
        if getattr(getattr(exc, "resp", None), "status", None) == 404:
            return {"ok": True, "exists": False}
        return outcome.failure(exc, "Calendar lookup error")


def create_event(summary: str, start_iso: str, end_iso: str = "", description: str = "",
                 tz: str = DEFAULT_TZ, idempotency_key: str = "") -> dict:
    """Create a calendar event (a reminder the user approved).

    Pass `idempotency_key` identifying the LOGICAL operation (e.g. the user and
    task the reminder is about). Retrying with the same key returns the existing
    event instead of creating a second one.

    Returns `{ok, status, event_id, link, duplicate}`; `status` is one of
    outcome.DONE / FAILED / UNKNOWN. UNKNOWN means the event may exist - never
    report it to the person as "it did not happen".
    """
    svc = _service()
    if svc is None:
        return {"ok": False, "status": outcome.FAILED,
                "reason": "Calendar not connected - re-authorize to add the Calendar scope."}
    summary = sanitize_text(summary, MAX_SUMMARY)
    description = sanitize_text(description, MAX_DESCRIPTION)
    try:
        if not end_iso:
            end_iso = (datetime.fromisoformat(start_iso) + timedelta(minutes=30)).isoformat()
        body = {
            "summary": summary,
            "description": description,
            "start": {"dateTime": start_iso, "timeZone": tz},
            "end": {"dateTime": end_iso, "timeZone": tz},
            # Active notifications: reach the person at the time, and once shortly before,
            # so the reminder is not passive - it comes to them.
            "reminders": {
                "useDefault": False,
                "overrides": [
                    {"method": "popup", "minutes": 0},
                    {"method": "popup", "minutes": 10},
                    {"method": "email", "minutes": 0},
                ],
            },
        }
        if idempotency_key:
            body["id"] = event_id_for(idempotency_key)
        try:
            ev = svc.events().insert(calendarId="primary", body=body).execute()
        except Exception as exc:  # noqa: BLE001
            # 409 means our own deterministic id is already on the calendar: the
            # logical operation already happened. That is success, not failure.
            if idempotency_key and _is_conflict(exc):
                return {"ok": True, "status": outcome.DONE, "duplicate": True,
                        "event_id": body["id"],
                        "reason": "Reminder was already on the calendar; not duplicated."}
            raise
        return {"ok": True, "status": outcome.DONE, "duplicate": False,
                "event_id": ev.get("id"), "link": ev.get("htmlLink")}
    except Exception as exc:  # noqa: BLE001
        res = outcome.failure(exc, "Calendar error")
        if idempotency_key:
            res["event_id"] = event_id_for(idempotency_key)
        return res
