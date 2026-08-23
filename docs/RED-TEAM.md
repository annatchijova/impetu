<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright 2026 Anna Tchijova -->

# ÍMPETU red team assessment

Adversarial review of the authority an LLM decision actually holds over the real
world in this system. Scope: `agent/`, `server/`, and the deployment posture the
README prescribes. Conducted against the code at `f2c2542`.

The question was not "can the model say something wrong". It was: **when the model
decides, what does that decision reach, and under whose identity?**

## Method

Every finding below follows the same protocol:

1. an invariant the system declares about itself,
2. the minimal adversarial input or sequence,
3. the state the architecture says is impossible,
4. that state, actually reproduced against the real code,
5. the causal chain traced to specific lines before anything is called confirmed.

Google and Firestore were replaced with fakes **at the transport boundary only**,
so the real `gcal`, `gmail`, `state`, `nudge`, `tools` and `server.main` code paths
execute. The fakes model the real world separately from the response, which is what
makes finding F1 observable at all. `server.main` was booted through ADK and driven
with `starlette.testclient`.

## Thesis: three identity discontinuities

ÍMPETU distributes authority across three subsystems — durable state, caller
identity, and outbound side effects — but no single identity of operation spans
them. Every finding is an instance of one shape: **a logical identity exists,
travels most of the way, and is dropped exactly at the boundary where it would have
been load-bearing.**

| identity | created at | dropped at | what proceeds without it |
|---|---|---|---|
| `user_id` | caller (URL path / query param) | the Google boundary — `load_creds()` takes no argument | every Gmail and Calendar side effect |
| `task_id` | `state.py:113` | `nudge.py:43` | the calendar event it describes |
| note key | `remember()` | `agent.py:77` (`.values()`) | the system prompt it becomes |
| `event_id`, `draft_id` | Google | never persisted anywhere | deduplication, reconciliation, the activity trail |

The inbound identity is never carried. The outbound identity is never captured. The
provenance identity is never preserved.

## Findings

Severity reflects impact on a real deployment following the README's own deploy
command, which includes `--allow-unauthenticated`.

### F1 — Unauthenticated read and write against the token owner's Google account (critical)

The four tools that touch Google do not accept a user identity at all. This is
visible in their signatures:

| tool | carries identity | backend |
|---|---|---|
| `recall_context` … `set_address_preference` | yes, `tool_context` | Firestore, per user |
| `draft_email` | yes, `tool_context` | Firestore **and** Google |
| `search_email`, `read_email`, `get_today_schedule`, `schedule_reminder` | **no parameter at all** | Google, single global identity |

The partition is exact: identity stops precisely where Google begins.

`load_creds()` (`google_auth.py:27`) takes no argument and returns one process-wide
OAuth credential built from `GMAIL_TOKEN_JSON`, carrying `gmail.compose`,
`gmail.readonly` and `calendar.events`.

**Reproduced.** `POST /apps/agent/users/whoever-i-want/sessions` with no credential
returns 200. Tool calls in that session resolve `_user_id()` to the invented id for
the Firestore tools and to *nothing* for the Google tools, which answer from the
single token. `search_email("codigo")` returned the token owner's bank verification
code; `read_email` returned a full body containing a home address.

The attacker never needs a valid victim id. Any id works, because the inbox that
answers is always the owner's.

Chain: `README.md:152` (`--allow-unauthenticated`) → ADK route
`/apps/{app_name}/users/{user_id}/sessions` → `tools.py:182-198` (no `tool_context`)
→ `gmail.py:67` → `google_auth.py:27`.

### F2 — Confused deputy: per-user read, single-identity write (high)

`POST /nudge?user_id=alice` with only the scheduler secret returns 200. The caller
proves a relationship to the *scheduler*, never to Alice. Alice's private task text
returns in the HTTP response body and is written into the **token owner's** calendar,
with `{"method": "email"}` armed (`gcal.py:85`), so Google mails it to them.

The system holds two identities at once — logical (`alice`) and effective
(`owner(GMAIL_TOKEN_JSON)`) — and never checks any relation between them. This is
what makes it worse than a conventional IDOR: the victim's data does not merely
become readable, it egresses through a third party's channel.

Chain: `main.py:92` (unvalidated query param) → `nudge.py:40-44` → `gcal.py:89`.

### F3 — The `/nudge` guard fails open (high)

`if expected and x_nudge_token != expected` (`main.py:98`). With `NUDGE_TOKEN`
unset or empty, the entire check is skipped. **Reproduced:** no header, HTTP 200.
The comparison is also non-constant-time.

### F4 — `/nudge` has no idempotency key at all (high)

The hypothesis was that the key might be bound to the execution rather than the
logical task. It is worse: there is no key. `gcal.create_event` never sets `id` or
`iCalUID`, so Google mints a fresh identity per insert. The only thing resembling a
key is `when`, derived from `datetime.now()` at `main.py:100` — the instant of
invocation.

`task_id` is computed and available: `build_nudge` returns it (`nudge.py:35`) and
`place_nudge` discards it when calling `gcal` (`nudge.py:43`).

**Reproduced:** four concurrent POSTs, four calendar events, identical `start`, same
task. Duplication under retry is structural, not probabilistic.

### F5 — Tool result is not evidence of a side effect (high)

Declared invariant (`AGENTS.md` #5): *"Every tool with a side effect reports whether
it actually happened — it never fakes success."* The invariant guards the false
positive. The false negative is unguarded.

`gcal.py:91` and `gmail.py:50` are blanket `except Exception` handlers that collapse
three distinct states — *failed*, *unknown*, *succeeded but the response was lost* —
into `ok: False`. A post-commit timeout is indistinguishable from a 400.

**Reproduced**, with the real world holding the effect and the tool reporting failure:

| path | belief | reality |
|---|---|---|
| `gcal.create_event` | `ok=False` | one event, email notification armed |
| `gmail.create_draft` | `created=False` | one real draft |
| `state.save_task` | exception propagated | one committed document |

The next cycle then repeats the effect: three identical reminders, all reported to
the model as failures. In Firestore it never converges, because `save_task` mints
`task_id` before writing (`state.py:113`), so the retry creates a second document.
That duplicate is permanent: `recall_context` returns two open tasks and marking one
done never closes the other.

`draft_email` additionally performs two side effects with no atomicity
(`tools.py:145-147`): memory says the draft exists, the Gmail flag says it does not,
and Gmail has it.

Root cause is F9: nothing records what was created, so nothing can reconcile it.

### F6 — The activity trail invents side effects (medium)

With Gmail disconnected, `draft_email` degrades honestly — and the trail records
`"Drafted email: ..."` anyway. `state.remember()` infers the label from the `draft:`
key prefix (`state.py:163-164`) and `draft_email` writes memory *before* calling
Gmail.

This matters because `/api/state` publishes that trail and `docs/impetu.html` renders
it as the live evidence that side effects are real. `log_activity` also swallows all
exceptions (`state.py:203-204`), so entries can vanish. The record of side effects is
neither sound nor complete.

### F7 — Stored memory acquires instruction authority; the transition is one line (high)

`agent.py:77` does three things at once:

```python
lines.append(f"- Learned about them: {v}")
```

- renders from `.values()`, discarding the key — the only provenance that existed;
- reframes a stored string as a fact, under the heading
  `"# What you already remember about THIS user"`;
- and `agent.py:94` concatenates the block onto `SYSTEM_INSTRUCTION`, placing it in
  system position, below and therefore apparently excepting the eight rules.

`remember`, `note_what_worked` and `set_address_preference` all take model-authored
strings with no schema, allowlist, length cap, or writer field. `set_address_preference`
explicitly authorises writing durable state on inference alone. The model therefore
authors its own future system prompt, and no stored note records who wrote it or
where it came from.

This is not classical prompt injection. The relevant question is whether an
untrusted observation can become durable state that later holds greater epistemic
authority than the source it came from. It can, and the promotion happens at
`agent.py:77`.

Two amplifiers, both reproduced:

- **Silent eviction.** `[:5]` — 13 notes stored, 5 reach the prompt, chosen by dict
  ordering the code does not control. A model told to keep calling `remember()`
  evicts preferences the person actually stated.
- **Unbounded volume.** One 20 000-character note produces a memory block three
  times the size of the entire ruleset.

The untrusted input channels are `read_email` (returns `body[:4000]` of any message
anyone can send), `search_email` (attacker-controlled `From` display names) and
`google_search`. Nothing in the code distinguishes "the person said this" from "an
email said this".

### F8 — Untrusted durable state reaches an outbound channel with no model in the loop (medium)

`build_nudge` calls no model. It interpolates `task['title']` and the step text
straight into the event summary and description, and `create_event` arms an email
notification. Confirmed passthrough with no transformation, escaping, or length
limit: newlines, carriage returns, control characters, the U+202E RTL override,
URLs, and HTML.

**Honest negative:** the event body is a dict literal with fixed keys
(`gcal.py:73-88`). Stored values reach only `summary` and `description`. There is no
field injection and no path to `attendees`, `conferenceData`, `source` or `gadget`.

The primitive is therefore not field injection but **borrowed sender reputation**: a
genuine Google Calendar notification, passing SPF/DKIM/DMARC, carrying
attacker-chosen text and URLs, delivered to the token owner. How Google renders
`description` in that mail (HTML versus plain, link autolinking) was **not tested**
and must not be claimed without a live check.

`schedule_reminder` takes all three arguments from the model, with no bound on
`when_iso`; events can be placed years out or in the past. Malformed values degrade
honestly.

### F9 — Outbound identity is never captured (root cause)

`event_id` (`gcal.py:90`) and `draft_id` (`gmail.py:49`) are returned by Google,
handed to the model, and persisted nowhere. The system keeps no record of what it
created in the outside world.

F4 (cannot deduplicate), F5 (cannot reconcile belief against reality) and F6 (cannot
verify its own trail) are all consequences of this single omission.

### F10 — Divergent store instances in fallback mode (low)

`tools.py:24` and `nudge.py:21` each construct a `Store()`; `tools._store is
nudge._store` is `False`. Harmless against Firestore, which is shared. In the
in-memory fallback, `/nudge` and `/api/state` read a different store than the agent
tools write to.

## What was not tested

Stated so no reader over-reads the above.

- **Gemini was never called.** No Vertex credentials were available. F7 establishes
  that stored data reaches system-prompt position and that `build_nudge` reaches
  egress with no model involved. It does **not** establish that Gemini complies with
  any particular note. The `build_nudge` half needs no model and is fully confirmed;
  the compliance half is an authority path, not an observed behaviour.
- **Google's APIs are simulated.** That a non-idempotent POST can commit and then
  fail its response is a standard property, not something observed against Google.
  What is confirmed against real code is the consequence: if it happens, the code
  reports `ok=False` and the next cycle duplicates.
- **Cloud Scheduler's default retry policy was not verified.** F4 does not depend on
  it; any retry, manual re-run, or concurrent instance produces the duplicate.
- **Calendar notification rendering was not observed**, as noted in F8.

## Remediation

See `docs/RED-TEAM-FIXES.md` for the patches applied against these findings and the
regression tests that hold them closed.
