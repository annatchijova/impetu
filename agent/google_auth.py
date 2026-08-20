# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Anna Tchijova
"""Shared Google OAuth for ÍMPETU: one token, the scopes Gmail and Calendar need.

One consent grants both: create Gmail drafts (never send) and read/create Calendar
events (gentle reminders). Never touches the inbox contents; never sends mail.
If the token is missing or lacks a scope, callers degrade honestly.
"""

from __future__ import annotations

import os
from pathlib import Path

SCOPES = [
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/calendar.events",
]

_ROOT = Path(__file__).resolve().parent.parent
TOKEN_PATH = os.environ.get("GMAIL_TOKEN_PATH", str(_ROOT / "gmail_token.json"))
CLIENT_SECRET_PATH = os.environ.get("GMAIL_CLIENT_SECRET", str(_ROOT / "client_secret.json"))


def load_creds():
    """Return valid OAuth credentials, or None if not connected."""
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
    return load_creds() is not None
