# AGENTS.md

Guidance for any AI coding agent (Claude Code, Cursor, etc.) working on this repo.
Human contributors: this is a good orientation too.

## What this is

ÍMPETU is a collaborative agent for autistic/ADHD minds. Thesis: **starting is the
hard problem, not planning** — every part exists to lower the activation energy of
beginning. Built on Google ADK + Gemini 3.5 for the All Things Agentic hackathon
(Collaborative Partner track). See `README.md` for the pitch and `docs/ROADMAP.md`
for the sequenced plan.

## Setup, run, verify

```bash
pip install -r requirements.txt          # ADK 2.1.0, firestore, fastapi, uvicorn
cp .env.example .env                      # Vertex AI config (no secrets; ADC does auth)
gcloud auth application-default login     # once, for Vertex credentials
python3 try_it.py "whatever you've been putting off"   # one real turn
IMPETU_FORCE_MEMORY=1 python3 try_it.py "..."           # skip Firestore, use fallback
adk web --port 8010 .                     # browser chat UI, pick the "agent" app
```

Auth is **Vertex AI**, not the AI Studio API key: the free tier is 20 requests/day,
too little for development. `.env` sets `GOOGLE_GENAI_USE_VERTEXAI=TRUE`, the project,
and `GOOGLE_CLOUD_LOCATION=global` (Gemini 3.5 lives on the global Vertex endpoint).

There is no unit-test suite yet. **Verify any change to the agent by running a real
turn** and reading the output — do not claim it works from inspection. For prompt or
memory changes, run a *two-turn, same-session* check (see `try_it.py`) to confirm the
agent adapts (e.g. captures él/ella/elle and uses it).

## Architecture

```
agent/prompts.py   the 8 co-regulation rules (the soul) + hard boundaries
agent/tools.py     real-action tools; each returns a `persisted` flag
agent/state.py     Firestore working memory + honest in-memory fallback
agent/agent.py     LlmAgent; instruction is DYNAMIC (injects per-user state)
try_it.py          local runner
```

- Model: `MODEL` env, default `gemini-3.5-flash`. Must stay Gemini 3.5+ (hackathon rule).
- State: Firestore is the source of truth; the in-memory fallback is deliberate and
  must stay honest (never report a write as persisted when it was not).

## Product invariants — DO NOT break these when editing

These are not style preferences; they are the product. A prompt edit that violates
one is a regression even if it "reads nicer":

1. **No shame, ever.** Missing a task is data, not failure. No nagging, no guilt.
2. **No crisis-hotline handoff.** A struggling user is kept company on the concrete
   next step, not deflected to a helpline. This is deliberate and load-bearing.
3. **One atomic step at a time.** Never dump a full plan unprompted.
4. **Negotiate, never command.** Offer and ask; the user can always say no. No
   "you have to / you should". (Autonomy-preserving; demand-avoidance aware.)
5. **Honest degradation.** Every tool with a side effect reports whether it actually
   happened (`persisted`, `gmail_draft_created`, ...). Never fake success.
6. **Respect address preference.** Use the stored él/ella/elle; never slash forms
   like "bloqueado/a".

## Conventions

- **Repo language is English** — all code, comments, docstrings, docs, and commit
  messages. (Conversations with the maintainer happen in Spanish; the repo does not.)
- **No emojis** anywhere in the repo or generated output.
- **License header on every new source file:**
  ```python
  # SPDX-License-Identifier: Apache-2.0
  # Copyright 2026 Anna Tchijova
  ```
- **Never commit a secret.** Keys live in the environment / Secret Manager, never in
  the repo. `.env` is gitignored.
- New tools go in `agent/tools.py` and get appended to `ALL_TOOLS`; keep the docstring
  written *for the model* (it is the tool's contract) and instruct honest reporting.

## Git discipline

- Branch: `master`. Commit messages explain *why*, in English, with the trailer
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- **Forbidden:** `rebase`, interactive rebase / squash, and `push --force` (any form).
  Forward-only history: commit, merge, revert.
- Do not commit or push unless the maintainer asks.
- Patch surgically; do not rewrite a file from memory. Re-read before editing.
