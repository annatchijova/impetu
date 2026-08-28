# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Anna Tchijova
"""One-time Gmail authorization for ÍMPETU.

Prerequisite: create an OAuth 2.0 Client ID of type "Desktop app" in the Google
Cloud console (project vigia-497422) and download it as `client_secret.json` into
this folder. Then run:

    python3 setup_gmail.py

It opens a browser for consent and writes `gmail_token.json` (gitignored). After
that, draft_email creates real drafts in your Gmail.

To connect ONE PERSON's own account instead of the shared token, pass their
user_id. That writes `tokens/<user_id>.json`, which ÍMPETU prefers over the
shared token, so their Gmail and Calendar side effects land on their own account
and they need no IMPETU_OWNER_USER_ID grant:

    python3 setup_gmail.py alice

In production the same JSON belongs in Secret Manager as
`impetu-google-token-<user_id>` (see agent/google_auth.py).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

from agent.google_auth import (CLIENT_SECRET_PATH, SCOPES, TOKEN_DIR, TOKEN_PATH,
                               safe_user_key)


def main(user_id: str = "") -> None:
    if not os.path.exists(CLIENT_SECRET_PATH):
        print(f"Missing {CLIENT_SECRET_PATH}")
        print("Create a 'Desktop app' OAuth client in the Cloud console and download it here.")
        return
    # Fixed loopback port + no auto-open: works even with no default browser. The URL
    # is printed so it can be opened manually; the redirect returns to localhost:PORT.
    port = int(os.environ.get("GMAIL_OAUTH_PORT", "8766"))
    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_PATH, SCOPES)
    creds = flow.run_local_server(
        host="localhost",
        port=port,
        open_browser=False,
        authorization_prompt_message="\n=== OPEN THIS URL TO AUTHORIZE ===\n{url}\n",
        success_message="Impetu is connected to Gmail. You can close this tab.",
    )
    if user_id:
        key = safe_user_key(user_id)
        if not key:
            print(f"Refusing user id {user_id!r}: use lowercase letters, digits, '-' or '_'.")
            return
        Path(TOKEN_DIR).mkdir(parents=True, exist_ok=True)
        out = Path(TOKEN_DIR) / f"{key}.json"
        out.write_text(creds.to_json())
        out.chmod(0o600)
        print(f"Connected {key}'s own Google account. Token saved to {out}.")
        print("Their Gmail and Calendar actions now land on their own account.")
        return

    with open(TOKEN_PATH, "w") as f:
        f.write(creds.to_json())
    print(f"Gmail connected. Token saved to {TOKEN_PATH}. draft_email now creates real drafts.")
    print("This is the SHARED token: only IMPETU_OWNER_USER_ID may use it.")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "")
