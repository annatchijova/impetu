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
import os
from email.message import EmailMessage
from pathlib import Path

# gmail.compose is the least scope that can create drafts. We never call send.
SCOPES = ["https://www.googleapis.com/auth/gmail.compose"]

_ROOT = Path(__file__).resolve().parent.parent
TOKEN_PATH = os.environ.get("GMAIL_TOKEN_PATH", str(_ROOT / "gmail_token.json"))
CLIENT_SECRET_PATH = os.environ.get("GMAIL_CLIENT_SECRET", str(_ROOT / "client_secret.json"))


def _load_creds():
    """Return valid OAuth credentials, or None if Gmail is not connected."""
    if not os.path.exists(TOKEN_PATH):
        return None
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials

        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(TOKEN_PATH, "w") as f:
                f.write(creds.to_json())
        return creds if (creds and creds.valid) else None
    except Exception:  # noqa: BLE001 - a broken token must not crash a turn
        return None


def is_connected() -> bool:
    return _load_creds() is not None


def _build_raw(to: str, subject: str, body: str) -> str:
    msg = EmailMessage()
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    return base64.urlsafe_b64encode(msg.as_bytes()).decode()


def create_draft(to: str, subject: str, body: str) -> dict:
    """Create a Gmail draft. Returns {created, draft_id?} or {created: False, reason}."""
    creds = _load_creds()
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
