<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright 2026 Anna Tchijova -->

# Remediation for docs/RED-TEAM.md

One principle drives every patch here, because every finding was an instance of
one defect: **an operation must carry the same identity from the caller all the
way to the side effect, and must record what it created.**

## New configuration (all fail-closed)

| variable | meaning | unset |
|---|---|---|
| `IMPETU_OWNER_USER_ID` | the one `user_id` allowed to reach the shared Google token | Gmail and Calendar are disabled entirely |
| `IMPETU_ACCESS_TOKEN` | required on the agent routes (`X-Impetu-Token` or bearer) | routes closed, unless the demo flag is set |
| `IMPETU_PUBLIC_DEMO=1` | run the agent routes publicly, pinned to the `demo` profile | — |
| `NUDGE_TOKEN` | authenticates the scheduler; now **required** | `/nudge` returns 503 |

A missing binding is the absence of permission, never permission.

## Patches by finding

**F1 — unauthenticated access to the token owner's Google account.**
`search_email`, `read_email`, `get_today_schedule` and `schedule_reminder` now
take `tool_context` like every other tool, and all four call `_google_guard`,
which resolves the session user and compares it to `IMPETU_OWNER_USER_ID`
(`agent/identity.py`). A session acting for anyone else is refused with a plain
reason. Separately, a middleware in `server/main.py` gates the ADK routes: with
`IMPETU_ACCESS_TOKEN` set it requires the token in constant time; with
`IMPETU_PUBLIC_DEMO=1` it allows only `user_id=demo`; with neither it returns 503.
The public demo therefore cannot reach Gmail or Calendar at all, because `demo`
is not the owner.

**F2 — confused deputy on `/nudge`.** The endpoint now performs two separate
checks, because they answer two different questions: `NUDGE_TOKEN` authenticates
the *caller* as the scheduler, and `IMPETU_OWNER_USER_ID` authorizes the *object*.
A `user_id` that is not the owner is refused, so one person's task text can no
longer land in another person's calendar and inbox.

**F3 — fail-open guard.** `NUDGE_TOKEN` is now required (503 when absent) and
compared with `hmac.compare_digest`.

**F4 — no idempotency key.** `gcal.create_event` accepts `idempotency_key` and
derives a deterministic Calendar event id from it (`event_id_for`, base32hex as
the API requires). `place_nudge` builds that key from the *logical* operation —
user, task, day — instead of the wall clock, and a 409 from Calendar is treated
as success with `duplicate: True`. Four concurrent nudges now produce one event.

**F5 — unknown reported as failed.** New `agent/outcome.py` gives every side
effect three states. A 4xx means the server rejected the request, so nothing
committed: `FAILED`. A 5xx or any transport error may have been applied and lost
its answer: `UNKNOWN`, carrying `uncertain: True` and explicit guidance not to
retry blind. `state.save_task` now derives `task_id` from the content rather than
`uuid4()`, so a retry after a lost response rewrites the same document instead of
creating a second open task that can never be closed.

**F6 — the trail invented side effects.** `state.remember` no longer infers an
activity label from a key prefix, and `draft_email` logs the Gmail attempt after
it happens, with its real status. Activity entries carry a `status` field.

**F7 — stored memory held instruction authority.** Notes are stored as records
carrying `source` (`user_stated`, `model_inferred`, `external`) and `at`, capped
at 500 characters, with explicit age-based eviction above 24 notes. The prompt
block is now framed as **data, not instructions**, keeps each note's key — its
only provenance — and states that a stored note can never authorise an action.
New rules 10 and 11 in `prompts.py` say the same to the model, and `search_email`
and `read_email` tag their results as untrusted. Unconfirmed side effects surface
in the prompt as a caution instead of being silently retried.

**F8 — untrusted state reaching an outbound channel.** `gcal.sanitize_text`
strips control and bidi characters, normalises newlines, and caps summary and
description before anything leaves for Google.

**F9 — outbound identity never captured.** `state.record_side_effect` persists
every `event_id` and `draft_id` under `users/{id}/side_effects/{external_id}`,
keyed by the external id so recording twice is a no-op.
`state.pending_side_effects` lists those whose outcome is still `unknown`.

**F10 — divergent stores.** Left as-is; it only affects the in-memory fallback
and fixing it properly means a shared module-level store, which is a separate
refactor. Documented rather than silently patched.

## Verification

`tests/test_red_team.py` replays each original attack and asserts it now fails —
18 tests, all passing. It fakes Google at the transport boundary only, so the real
`gcal`, `gmail`, `state`, `nudge`, `tools` and `server.main` code paths execute,
and the fake keeps the real world separate from the response so F5 stays
observable.

```
python3 tests/test_red_team.py
```

## What remains open

- **Per-user Google credentials.** The real fix for F1 and F2 is one OAuth token
  per person. Until then the deployment is genuinely single-tenant, and the owner
  guard makes that explicit and enforced rather than implicit and exploitable.
- **Real caller authentication.** `IMPETU_ACCESS_TOKEN` is a shared secret, not
  per-user identity. A production deployment wants IAP or an identity provider in
  front of the agent routes.
- **F5 reconciliation.** Unknown side effects are now recorded and surfaced, but
  nothing yet goes back to Google to ask whether the event or draft actually
  exists. The stored `external_id` is what makes that possible.
- Findings marked untested in `docs/RED-TEAM.md` remain untested.
