# ÍMPETU

A calm, collaborative agent for autistic and ADHD minds. Its whole design rests on
one thesis:

> **Starting is the hard problem, not planning.**

For an executive-dysfunction brain the plan is never the bottleneck; the activation
energy to *begin* is. Every part of ÍMPETU exists to lower that energy. It does not
just chat about what to do next: it negotiates the next step, drafts real outputs,
checks your calendar and inbox, remembers what works for you, and comes back on its
own with the next useful move. It is a proactive collaborator, not a passive chat
box.

## Why it feels agentic

- It asks what matters right now instead of dumping a full plan.
- It uses real tools: Gmail, Calendar, web search, memory, and scheduled nudges.
- It keeps working after the session ends, so the user does not have to restart.
- It reports truthfully when a side effect happened and when it did not.

## Canonical demo path

1. The user says they are stuck or overwhelmed.
2. ÍMPETU asks for one negotiated next step and a 1-to-5 energy rating.
3. It drafts something real, stores the memory, and schedules the next nudge.
4. Later, it comes back first with the next useful move.

## What the judge should notice

- There is a visible loop, not just a chat exchange.
- Real side effects are reported as side effects, not implied.
- The agent keeps context and returns later without being restarted.
- The demo can show visible states like draft created, memory saved, and follow-up scheduled.

## Judge shortcut

If you only have 30 seconds, read the canonical demo path and look for the visible states:
draft created, memory saved, follow-up scheduled, then the return later.

## Sample session

- User: "I'm overwhelmed and can't start."
- ÍMPETU: "Want one tiny next step, or do you want to rest first?"
- User: "One step."
- ÍMPETU: drafts the next step, saves the memory, and schedules the follow-up.

Built for the **All Things Agentic** hackathon — **Collaborative Partner** track.

**Live:** https://impetu-brkvglmi2a-uc.a.run.app
**Capabilities + architecture page:** [`docs/impetu.html`](docs/impetu.html) (bilingual, EN default)

---

## What it does

All eight of these are deployed and verified end to end.

- **One step at a time, negotiated.** Never a wall of steps, never an order. It offers
  the next move and you can change it or say no — some autistic people shut down when
  told what to do (demand avoidance). It talks to you like a capable adult; ADHD and
  autism are executive function, not intelligence, so no baby-talk and no infantilizing.
- **Does the scary 10%.** It writes the email in your voice — short, without repeating
  your name — and drops it as a real draft in your Gmail. You just review and send.
- **Long-term memory.** It remembers your open tasks, your energy, what framing works
  for you, and how you like to be addressed (él / ella / elle) — across sessions, so you
  never re-explain.
- **Looks up what you don't know.** When a real fact is missing (an address, a deadline,
  a procedure) it searches the web instead of inventing it — and says so if it can't find it.
- **Finds it in your inbox.** Ask "what was that address?" and it searches your own Gmail
  to find it. Read-only: it never sends, deletes, or changes anything.
- **Reads your day and schedules.** It checks what you already have today to keep the ask
  realistic, and creates reminders that actually reach you (popup and email, on time).
- **Comes to you.** A daily Cloud Scheduler job turns your open tasks into an active
  reminder and writes to you first — no app open. A purely reactive assistant is not
  enough for an ADHD brain.
- **Adapts to your energy, with a team behind the scenes.** It asks 1–5 and scales the
  step (including permission to rest, no guilt). Specialized sub-agents decompose and
  draft in the background, but you always talk to one coherent voice.

## How it works

The **LLM is in the decision path** by design here: Gemini reasons about your situation
and picks the action. Everything consequential — your memory, your drafts, your reminders
— lives in Google Cloud, not on your machine.

```
You (chat / browser)
      → Cloud Run (ADK server)
      → Vertex AI · Gemini 3.5   (decides)
      → tools: 10 functions + web search + 2 sub-agents
      → Firestore (memory)  ·  Gmail + Calendar (real action)
```

**The proactive loop** — runs entirely in Google Cloud, every day, with your computer off:

```
Cloud Scheduler (10:00 AR) → Cloud Run /nudge → Firestore (your open task) → Calendar (notifies you)
```

### Tech stack (all Google Cloud)

| Service | Role |
|---|---|
| **Gemini 3.5 (Vertex AI)** | the reasoning; picks the action |
| **Google ADK** | agent framework — `LlmAgent`, function tools, `AgentTool` sub-agents, `google_search` grounding |
| **Cloud Run** | hosts the agent + the `/nudge` endpoint |
| **Firestore** | durable working memory (with an honest in-memory fallback) |
| **Secret Manager** | the Gmail/Calendar OAuth token |
| **Cloud Scheduler** | fires the daily proactive nudge |
| **Gmail API · Calendar API** | real action (draft, read, schedule) |

### Project layout

```
agent/
  prompts.py      co-regulation rules + sub-agent instructions (the soul)
  agent.py        root LlmAgent + decomposer/drafter sub-agents; dynamic instruction
  tools.py        real-action tools; each reports whether its side effect happened
  state.py        Firestore working memory + honest in-memory fallback
  gmail.py        draft + inbox search (compose/readonly scopes; never sends)
  gcal.py         read the day + create notifying reminders
  google_auth.py  one OAuth token for all scopes; reads env (Secret Manager) or file
  nudge.py        proactive check-in composed from open tasks
server/main.py    Cloud Run app (ADK get_fast_api_app) + /nudge + /healthz
setup_gmail.py    one-time Gmail/Calendar OAuth consent
try_it.py         local CLI runner
docs/impetu.html  capabilities + architecture page (bilingual)
docs/ROADMAP.md   the build plan
```

## Run it locally

Auth is **Vertex AI** (real quota; the AI Studio free tier of 20 req/day is too small).

```bash
pip install -r requirements.txt
cp .env.example .env                    # Vertex config; no secrets, ADC handles auth
gcloud auth application-default login   # once

python3 try_it.py "whatever you've been putting off"   # one turn in the terminal
adk web --port 8010 .                                   # or a chat UI; pick the "agent" app
```

To enable Gmail/Calendar locally, create a **Desktop** OAuth client in the Cloud console,
save it as `client_secret.json`, then run `python3 setup_gmail.py` once.

## Deploy to Cloud Run

```bash
# One agent, one command (Vertex auth via the runtime service account — no API key):
gcloud run deploy impetu --source . --region us-central1 --allow-unauthenticated \
  --set-env-vars GOOGLE_GENAI_USE_VERTEXAI=TRUE,GOOGLE_CLOUD_PROJECT=<project>,GOOGLE_CLOUD_LOCATION=global,MODEL=gemini-3.5-flash

# Gmail/Calendar token as a secret (kept out of the image):
gcloud secrets create impetu-gmail-token --data-file=gmail_token.json
gcloud run services update impetu --region us-central1 \
  --set-secrets GMAIL_TOKEN_JSON=impetu-gmail-token:latest \
  --update-env-vars NUDGE_TOKEN=<random>,IMPETU_OWNER_USER_ID=<your-user-id>,IMPETU_PUBLIC_DEMO=1

# IMPETU_OWNER_USER_ID is the only user_id allowed to reach the shared Google
# token; everyone else is refused. IMPETU_PUBLIC_DEMO=1 keeps the public agent
# routes open but pinned to the "demo" profile (which cannot touch Gmail or
# Calendar). For a private deployment set IMPETU_ACCESS_TOKEN instead. All of
# these fail closed when unset - see docs/RED-TEAM.md.

# Proactive nudges: a scheduled call to /nudge (protected by NUDGE_TOKEN):
gcloud scheduler jobs create http impetu-nudge --location us-central1 \
  --schedule "0 10 * * *" --time-zone "America/Argentina/Buenos_Aires" \
  --uri "<service-url>/nudge?user_id=user" --http-method POST --headers "X-Nudge-Token=<random>"
```

The runtime service account needs Vertex AI User, Firestore access, and
`secretAccessor` on the token secret.

## Design principles (they never move)

- **No shame, ever.** Missing a step is information, not failure. No nagging, no guilt.
- **No crisis-hotline handoff.** A struggling person is kept company on the concrete next
  step, not deflected to a helpline.
- **Respect the person's intelligence.** Small steps lower activation energy; they are not
  about capability.
- **Honest degradation.** Every tool with a side effect reports whether it actually
  happened — it never fakes success, and never reports an uncertain outcome as a
  failure. No secret is ever committed to the repo.
- **One identity per operation.** The caller's identity travels all the way to the
  side effect, and every side effect's id is recorded. See [`docs/RED-TEAM.md`](docs/RED-TEAM.md)
  for the adversarial review this rule came out of, and
  [`docs/RED-TEAM-FIXES.md`](docs/RED-TEAM-FIXES.md) for the patches.

## License

Apache License 2.0 — see [LICENSE](LICENSE). Copyright 2026 Anna Tchijova.
