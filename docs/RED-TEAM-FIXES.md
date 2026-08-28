<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright 2026 Anna Tchijova -->

# Remediation for docs/RED-TEAM.md

One principle drives every patch here, because every finding was an instance of
one defect: **an operation must carry the same identity from the caller all the
way to the side effect, and must record what it created.**

## New configuration (all fail-closed)

| variable | meaning | unset |
|---|---|---|
| `IMPETU_TOKEN_SECRET_PREFIX` | Secret Manager prefix for per-person tokens (`impetu-google-token-`) | per-person tokens come only from `IMPETU_TOKEN_DIR` |
| `IMPETU_TOKEN_DIR` | local directory of per-person tokens, for development | defaults to `tokens/` |
| `IMPETU_OWNER_USER_ID` | the one `user_id` allowed to reach the **shared** token | anyone without a personal token gets no Google access |
| `IMPETU_ACCESS_TOKEN` | required on the agent routes (`X-Impetu-Token` or bearer) | routes closed, unless the demo flag is set |
| `IMPETU_PUBLIC_DEMO=1` | run the agent routes publicly, pinned to the `demo` profile | — |
| `NUDGE_TOKEN` | authenticates the scheduler; now **required** | `/nudge` returns 503 |

A missing binding is the absence of permission, never permission.

## Per-person Google credentials

This is the real fix for F1 and F2, and it is the audit's own thesis applied to
the worst case: the identity now reaches the credential instead of dying just
before it.

`load_creds(user_id)` resolves that person's own token first - Secret Manager
(`impetu-google-token-<user_id>`) in production, `tokens/<user_id>.json` for
development - and only falls back to the shared token otherwise. `user_id` is
threaded through every Gmail and Calendar function to that lookup, so a call can
no longer reach Google without saying who it is for.

The guard follows: someone who connected their own account needs no grant at all,
because the side effect lands on their own calendar and their own inbox and there
is no deputy to confuse. `IMPETU_OWNER_USER_ID` now governs only the shared-token
fallback. `setup_gmail.py <user_id>` performs the per-person consent.

Two things the caller-supplied `user_id` must never do, both tested:

- **Escape into a path or a secret name.** `safe_user_key` allows only
  `[a-z0-9][a-z0-9_-]{0,62}`; anything else has no personal token. Without this,
  adding per-user paths would have introduced a traversal the original code did
  not have.
- **Collide.** The id is refused rather than normalised, because lowercasing would
  map `Alice` and `alice` - two different people to Firestore - onto one Google
  token, recreating the exact defect in miniature.

Resolving a personal token can mean a Secret Manager round trip and the guard runs
on every Google tool call, so lookups are cached for 60 seconds, with
`forget_cached_tokens()` for the connect flow.

## Patches by finding

**F1 — unauthenticated access to the token owner's Google account.**
`search_email`, `read_email`, `get_today_schedule` and `schedule_reminder` now
take `tool_context` like every other tool, and all four call `_google_guard`,
which resolves the session user, admits them outright if they have their own
token, and otherwise compares them to `IMPETU_OWNER_USER_ID`
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

**F10 — divergent stores.** `state.get_store()` returns one lazily-created Store
for the process; `tools` and `nudge` both use it. This also removes the duplicate
Firestore health check that ran at import.

## Reconciliation: turning UNKNOWN into an answer

Recording an uncertain side effect was only half the fix. `agent/reconcile.py`
now goes back and asks:

- `gcal.get_event(event_id)` looks the event up by the deterministic id we chose,
  treating a 404 as "it never landed" and `status: cancelled` as deleted.
- `gmail.find_draft_by_subject(subject)` handles the harder case: a lost draft
  response never told us the draft id, so subject matching is the only way back
  to the truth. It cannot distinguish two drafts with the same subject, and says
  so - a hit means "probably yes", not proof.
- `state.resolve_side_effect` writes the answer back and the activity trail
  records that a previously uncertain action was settled.

It runs in two places, deliberately not on every turn: `place_nudge` reconciles
*before* creating anything new, so the scheduled loop converges instead of
accumulating doubt; and the agent can call `check_uncertain_actions` when the
person asks. Rule 11 in `prompts.py` tells the model never to redo an uncertain
action without calling it first.

## Verification

`tests/test_red_team.py` replays each original attack and asserts it now fails —
29 tests, all passing, and passing in randomised order so no test depends on
another's leftovers. Each was checked as a negative control: reverting the fix
turns the corresponding tests red, so they can actually fail. Reverting the
identity threading, for instance, produced `[None, 'alice']` - the discontinuity
reappearing in `gcal` while `gmail` still carried it. It fakes Google at the transport boundary only, so the real
`gcal`, `gmail`, `state`, `nudge`, `tools` and `server.main` code paths execute,
and the fake keeps the real world separate from the response so F5 stays
observable.

```
python3 tests/test_red_team.py
```

## What remains open

- **Real caller authentication.** This is now the largest remaining gap.
  `IMPETU_ACCESS_TOKEN` is a shared secret, not per-user identity, so the system
  still trusts whatever `user_id` a permitted caller claims. Per-person tokens
  bound the damage - a caller claiming someone else's id cannot reach that
  person's Google account without their token - but Firestore state is still
  addressed by an unverified id. A production deployment wants IAP or an identity
  provider in front of the agent routes, and that is an infrastructure decision,
  not a code change.
- **Nobody has connected a personal token yet.** The mechanism is tested, but the
  deployment described in the README still runs on the shared token, so it remains
  single-tenant in practice until `setup_gmail.py <user_id>` is run per person.
- **Gmail reconciliation is best-effort.** Matching on subject cannot distinguish
  two drafts with the same subject. Resolving by id would need Gmail to return one
  before the response is lost, which it cannot.
- **The prompt-side mitigations for F7 are reasoned, not verified.** Rules 10 and
  11, the DATA framing, and the untrusted tags have not been tested against a live
  Gemini, because no Vertex credentials were available. The `build_nudge` half of
  F7/F8 needs no model and is fully covered by tests; model compliance is not.
- Findings marked untested in `docs/RED-TEAM.md` remain untested.
