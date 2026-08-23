# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Anna Tchijova
"""Google OAuth for ÍMPETU: per-person tokens, with a shared-token fallback.

One consent grants both: create Gmail drafts (never send) and read/create Calendar
events (gentle reminders). Never sends mail.

Credentials resolve PER USER, because that is the real fix for the worst finding
in docs/RED-TEAM.md: a single process-wide token meant every Google side effect
landed on one person's account no matter who asked, so the identity died at this
boundary. `load_creds(user_id)` now looks for that person's own token first:

  1. Secret Manager, `{IMPETU_TOKEN_SECRET_PREFIX}{user_id}` - the right home for
     a refresh token, and what a multi-person deployment should use.
  2. A local per-user file under `IMPETU_TOKEN_DIR`, for development.
  3. The legacy shared token (`GMAIL_TOKEN_JSON` or `gmail_token.json`), which
     only `IMPETU_OWNER_USER_ID` may use - see `agent/identity.py`.

`user_id` reaches here from the caller, so it is never used raw in a secret name
or a file path: `safe_user_key` rejects anything outside [a-z0-9_-].
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

SCOPES = [
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.events",
]

_ROOT = Path(__file__).resolve().parent.parent
TOKEN_PATH = os.environ.get("GMAIL_TOKEN_PATH", str(_ROOT / "gmail_token.json"))
CLIENT_SECRET_PATH = os.environ.get("GMAIL_CLIENT_SECRET", str(_ROOT / "client_secret.json"))

TOKEN_DIR = os.environ.get("IMPETU_TOKEN_DIR", str(_ROOT / "tokens"))
SECRET_PREFIX = os.environ.get("IMPETU_TOKEN_SECRET_PREFIX", "impetu-google-token-")

PERSONAL = "personal"
SHARED = "shared"

_SAFE_KEY = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")

# Resolving a personal token can mean a Secret Manager round trip, and the
# identity guard runs on every Google tool call. Cache briefly so the guard costs
# nothing per call, but expire fast enough that someone who has just connected
# their account is not locked out for long.
_TOKEN_TTL_SECONDS = 60.0
_token_cache: dict = {}


def _cached(key):
    hit = _token_cache.get(key)
    if hit and (time.monotonic() - hit[0]) < _TOKEN_TTL_SECONDS:
        return hit[1]
    return None


def forget_cached_tokens() -> None:
    """Drop the personal-token cache (used by tests and after a new connection)."""
    _token_cache.clear()


def safe_user_key(user_id):
    """A user id usable in a secret name or filename, or None.

    The id comes from the caller, so anything outside a strict allowlist is
    refused rather than escaped - no traversal, no secret-name confusion. The id
    is NOT normalised: lowercasing it would map "Alice" and "alice" - two
    different people as far as Firestore is concerned - onto one Google token,
    which is the very collision this module exists to prevent. An id that does
    not already fit the allowlist simply has no personal token.
    """
    key = (user_id or "").strip()
    return key if _SAFE_KEY.match(key) else None


def _personal_token_info(user_id):
    """This person's own token, from Secret Manager or a local dev file."""
    key = safe_user_key(user_id)
    if not key:
        return None
    cached = _cached(key)
    if cached is not None:
        return cached or None

    info = _fetch_personal_token(key)
    _token_cache[key] = (time.monotonic(), info or False)
    return info


def _fetch_personal_token(key):
    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if project:
        try:
            from google.cloud import secretmanager  # type: ignore

            client = secretmanager.SecretManagerServiceClient()
            name = f"projects/{project}/secrets/{SECRET_PREFIX}{key}/versions/latest"
            payload = client.access_secret_version(name=name).payload.data.decode("utf-8")
            return json.loads(payload)
        except Exception:  # noqa: BLE001 - absent or unreadable: fall through
            pass

    path = Path(TOKEN_DIR) / f"{key}.json"
    try:
        if path.is_file():
            return json.loads(path.read_text())
    except Exception:  # noqa: BLE001
        return None
    return None


def has_personal_token(user_id) -> bool:
    """True when this person has connected their OWN Google account."""
    return _personal_token_info(user_id) is not None


def credential_source(user_id):
    """Which credential a call for `user_id` would use: PERSONAL, SHARED, or None."""
    if has_personal_token(user_id):
        return PERSONAL
    if os.environ.get("GMAIL_TOKEN_JSON") or os.path.exists(TOKEN_PATH):
        return SHARED
    return None


def load_creds(user_id=None):
    """Return valid OAuth credentials for `user_id`, or None if not connected.

    Prefers that person's own token; falls back to the shared one. Callers must
    still pass `agent.identity.google_identity_check` first - this function
    resolves a credential, it does not decide who is allowed one.
    """
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials

        info = _personal_token_info(user_id) if user_id else None
        raw = None
        if info is None:
            raw = os.environ.get("GMAIL_TOKEN_JSON")
            if raw:
                info = json.loads(raw)
            elif os.path.exists(TOKEN_PATH):
                with open(TOKEN_PATH) as f:
                    info = json.load(f)
            else:
                return None

        creds = Credentials.from_authorized_user_info(info, SCOPES)
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            if not raw:
                try:
                    with open(TOKEN_PATH, "w") as f:
                        f.write(creds.to_json())
                except OSError:
                    pass  # read-only filesystem (e.g. Cloud Run) - refresh stays in memory
        return creds if (creds and creds.valid) else None
    except Exception:  # noqa: BLE001 - a broken token must not crash a turn
        return None


def is_connected(user_id=None) -> bool:
    return load_creds(user_id) is not None
