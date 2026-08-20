# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Anna Tchijova
"""One-time Gmail authorization for ÍMPETU.

Prerequisite: create an OAuth 2.0 Client ID of type "Desktop app" in the Google
Cloud console (project vigia-497422) and download it as `client_secret.json` into
this folder. Then run:

    python3 setup_gmail.py

It opens a browser for consent and writes `gmail_token.json` (gitignored). After
that, draft_email creates real drafts in your Gmail.
"""

from __future__ import annotations

import os

from google_auth_oauthlib.flow import InstalledAppFlow

from agent.gmail import CLIENT_SECRET_PATH, SCOPES, TOKEN_PATH


def main() -> None:
    if not os.path.exists(CLIENT_SECRET_PATH):
        print(f"Missing {CLIENT_SECRET_PATH}")
        print("Create a 'Desktop app' OAuth client in the Cloud console and download it here.")
        return
    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_PATH, SCOPES)
    creds = flow.run_local_server(port=0)
    with open(TOKEN_PATH, "w") as f:
        f.write(creds.to_json())
    print(f"Gmail connected. Token saved to {TOKEN_PATH}. draft_email now creates real drafts.")


if __name__ == "__main__":
    main()
