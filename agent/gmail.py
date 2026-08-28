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

from . import outcome
from .google_auth import is_connected, load_creds  # noqa: F401 - re-exported for callers


def _build_raw(to: str, subject: str, body: str) -> str:
    msg = EmailMessage()
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    return base64.urlsafe_b64encode(msg.as_bytes()).decode()


def create_draft(to: str, subject: str, body: str, user_id=None) -> dict:
    """Create a Gmail draft.

    Returns `{created, status, draft_id?}`. `status` is outcome.DONE / FAILED /
    UNKNOWN; UNKNOWN means the draft may have been created even though we did not
    get the answer, so it must never be reported as "it did not happen".
    """
    creds = load_creds(user_id)
    if creds is None:
        return {
            "created": False,
            "status": outcome.FAILED,
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
        return {"created": True, "status": outcome.DONE, "draft_id": draft.get("id")}
    except Exception as exc:  # noqa: BLE001 - report failure honestly, never crash
        res = outcome.failure(exc, "Gmail API error")
        # `created` stays False for backwards compatibility, but `status` tells
        # the truth: UNKNOWN means a draft may exist. See docs/RED-TEAM.md F5.
        res["created"] = False
        return res


def find_draft_by_subject(subject: str, user_id=None) -> dict:
    """Best-effort: is there a draft with this subject?

    When a draft creation loses its response we never learn the draft id, so an
    id lookup is impossible and this is the only way back to the truth. It
    matches on subject, so identical subjects are indistinguishable - the caller
    must treat a hit as "probably yes", not proof. See docs/RED-TEAM.md F5.
    """
    creds = load_creds(user_id)
    if creds is None:
        return {"ok": False, "reason": "Gmail not connected."}
    try:
        from googleapiclient.discovery import build

        svc = build("gmail", "v1", credentials=creds, cache_discovery=False)
        listing = svc.users().drafts().list(userId="me", maxResults=50).execute()
        wanted = (subject or "").strip()
        for d in listing.get("drafts", []) or []:
            full = svc.users().drafts().get(userId="me", id=d["id"], format="metadata").execute()
            headers = full.get("message", {}).get("payload", {}).get("headers", [])
            got = next((h["value"] for h in headers if h.get("name") == "Subject"), "")
            if got.strip() == wanted:
                return {"ok": True, "exists": True, "draft_id": d["id"]}
        return {"ok": True, "exists": False}
    except Exception as exc:  # noqa: BLE001
        return outcome.failure(exc, "Gmail draft lookup error")


def _extract_plain(payload: dict) -> str:
    """Pull the plain-text body out of a Gmail message payload, recursively."""
    if payload.get("mimeType") == "text/plain":
        data = payload.get("body", {}).get("data")
        if data:
            return base64.urlsafe_b64decode(data).decode("utf-8", "replace")
    for part in payload.get("parts", []) or []:
        text = _extract_plain(part)
        if text:
            return text
    return ""


def search_messages(query: str, max_results: int = 5, user_id=None) -> dict:
    """Search the person's own inbox. Returns matches (from, subject, date, snippet).

    Read-only: this only looks; it never sends, deletes, or changes anything.
    """
    creds = load_creds(user_id)
    if creds is None:
        return {"ok": False, "reason": "Gmail not connected - re-authorize to add the read scope."}
    try:
        from googleapiclient.discovery import build

        svc = build("gmail", "v1", credentials=creds, cache_discovery=False)
        ids = svc.users().messages().list(userId="me", q=query, maxResults=max_results).execute()
        results = []
        for m in ids.get("messages", []):
            full = (
                svc.users()
                .messages()
                .get(userId="me", id=m["id"], format="metadata",
                     metadataHeaders=["From", "Subject", "Date"])
                .execute()
            )
            h = {x["name"]: x["value"] for x in full.get("payload", {}).get("headers", [])}
            results.append({
                "id": m["id"],
                "from": h.get("From", ""),
                "subject": h.get("Subject", ""),
                "date": h.get("Date", ""),
                "snippet": full.get("snippet", ""),
            })
        return {"ok": True, "count": len(results), "results": results}
    except Exception as exc:  # noqa: BLE001
        return outcome.failure(exc, "Gmail read error (is the readonly scope authorized?)")


def get_message(message_id: str, user_id=None) -> dict:
    """Read the full plain-text body of one message (by id from search_messages)."""
    creds = load_creds(user_id)
    if creds is None:
        return {"ok": False, "reason": "Gmail not connected - re-authorize to add the read scope."}
    try:
        from googleapiclient.discovery import build

        svc = build("gmail", "v1", credentials=creds, cache_discovery=False)
        full = svc.users().messages().get(userId="me", id=message_id, format="full").execute()
        h = {x["name"]: x["value"] for x in full.get("payload", {}).get("headers", [])}
        body = _extract_plain(full.get("payload", {}))
        return {
            "ok": True,
            "from": h.get("From", ""),
            "subject": h.get("Subject", ""),
            "body": body[:4000],
        }
    except Exception as exc:  # noqa: BLE001
        return outcome.failure(exc, "Gmail read error")
