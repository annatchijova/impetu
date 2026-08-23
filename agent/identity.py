# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Anna Tchijova
"""One identity of operation, carried across every boundary.

The audit in `docs/RED-TEAM.md` found the same defect three times: a logical
identity exists, travels most of the way, and is dropped exactly at the boundary
where it would have been load-bearing. The worst instance is here - the Gmail and
Calendar credentials are a single process-wide token (`GMAIL_TOKEN_JSON`), so
every Google side effect lands on ONE person's account no matter which `user_id`
asked for it.

Until ÍMPETU stores per-user OAuth tokens, that single token means the deployment
is single-tenant, and this module makes that explicit and enforced instead of
implicit and exploitable:

  IMPETU_OWNER_USER_ID   the one user_id permitted to reach Google.

Fail-closed: if it is unset, no Google side effect is allowed at all. A missing
binding is not permission, it is the absence of permission.
"""

from __future__ import annotations

import os

ENV_OWNER = "IMPETU_OWNER_USER_ID"


class IdentityError(RuntimeError):
    """Raised when an operation cannot prove which person it acts for."""


def owner_user_id():
    value = (os.environ.get(ENV_OWNER) or "").strip()
    return value or None


def google_identity_check(user_id):
    """Return None if `user_id` may use the shared Google token, else a reason.

    The shared token authenticates exactly one Google account. Anyone else
    reaching it is a confused deputy: their read answers from the owner's inbox
    and their write lands on the owner's calendar.
    """
    owner = owner_user_id()
    if owner is None:
        return (
            f"Google actions are disabled: {ENV_OWNER} is not set, so this "
            "deployment cannot prove whose account the shared token belongs to."
        )
    if not user_id:
        return "Google actions need a resolved user id; this session has none."
    if user_id != owner:
        return (
            "Google actions are limited to the account that owns the connected "
            "token. This session is acting for a different person, so Gmail and "
            "Calendar are not available to it."
        )
    return None
