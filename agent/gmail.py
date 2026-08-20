# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Anna Tchijova
"""Gmail integration: create a real draft the user can open and edit.

This is the "scary 10%" made real. It NEVER sends - it only creates a draft, so
pressing send always stays a human act. If Gmail is not connected (no OAuth token
yet), every function degrades honestly: it reports `created=False` with a reason,
and never raises into the calling tool.

Auth is OAuth on behalf of the user (personal Gmail cannot use a service account).
Run `setup_gmail.py` once to produce the token; see the README/checklist.
"""

from __future__ import annotations

import base64
from email.message import EmailMessage

from .google_auth import is_connected, load_creds  # noqa: F401 - re-exported for callers


def _build_raw(to: str, subject: str, body: str) -> str:
    msg = EmailMessage()
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    return base64.urlsafe_b64encode(msg.as_bytes()).decode()


def create_draft(to: str, subject: str, body: str) -> dict:
    """Create a Gmail draft. Returns {created, draft_id?} or {created: False, reason}."""
    creds = load_creds()
    if creds is None:
        return {
            "created": False,
            "reason": "Gmail not connected yet - run setup_gmail.py once to authorize.",
        }
    try:
        from googleapiclient.discovery import build

        service = build("gmail", "v1", credentials=creds, cache_discovery=False)
        raw = _build_raw(to, subject, body)
        draft = (
            service.users()
            .drafts()
            .create(userId="me", body={"message": {"raw": raw}})
            .execute()
        )
        return {"created": True, "draft_id": draft.get("id")}
    except Exception as exc:  # noqa: BLE001 - report failure honestly, never crash
        return {"created": False, "reason": f"Gmail API error: {exc}"}
