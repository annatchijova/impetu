# ÍMPETU — Devpost submission draft

Draft copy for the Devpost form. Everything here is in English (repo language).
Paste the sections into the matching fields; edit freely.

- **Category:** Collaborative Partner
- **Project URL (hosted):** https://impetu-brkvglmi2a-uc.a.run.app
- **Repository:** https://github.com/annatchijova/impetu
- **Architecture diagram:** `docs/architecture.svg` (upload this)

---

## Elevator pitch (one line)

A calm, proactive agent for autistic and ADHD minds that lowers the activation
energy to *start* — it negotiates one next step, does the scary 10%, and comes back
on its own the next day.

---

## Inspiration / the problem

For an executive-dysfunction brain the plan is never the bottleneck; the activation
energy to *begin* is. Most assistants dump a full plan and wait — which is exactly
what a stuck brain cannot act on. ÍMPETU is built on one thesis: **starting is the
hard problem, not planning.** Every feature exists to lower the energy to begin, and
to keep company on the concrete next step instead of deflecting to a helpline.

---

## Features and functionality

- **One step at a time, negotiated.** It offers the next micro-step and you can change
  it or say no — never a wall of steps, never an order (some autistic people shut down
  when told what to do). It talks to you like a capable adult; no infantilizing.
- **Does the scary 10%.** It writes the email in your voice — short, no repeated name —
  and drops it as a **real Gmail draft**. You just review and send (it never sends).
- **Long-term memory across sessions.** Remembers your open tasks, last energy level,
  what framing works for you, and how you like to be addressed (él / ella / elle), so
  you never re-explain. Backed by Firestore, with an honest in-memory fallback.
- **Looks up what you don't know.** When a real fact is missing (an address, a deadline,
  a procedure) it uses grounded web search instead of inventing it — and says so if it
  can't find it.
- **Finds it in your inbox.** Read-only Gmail search to answer "what was that address?"
  — it never sends, deletes, or changes anything.
- **Reads your day and schedules.** Checks today's calendar to keep the ask realistic,
  and creates reminders that actually reach you (popup + email, on time).
- **Comes to you.** A daily Cloud Scheduler job turns your open task into an active
  calendar reminder and reaches out first — no app open, computer off.
- **A team behind one voice.** Specialized sub-agents (decomposer, drafter) work in the
  background; you always talk to a single coherent voice.
- **Honest degradation.** Every tool with a side effect reports whether it actually
  happened — it never fakes success.

---

## Technologies used

- **Gemini 3.5 (Vertex AI)** — the reasoning; picks the action (LLM in the decision path
  by design).
- **Google ADK** — agent framework: `LlmAgent`, function tools, `AgentTool` sub-agents,
  `google_search` grounding.
- **Cloud Run** — hosts the ADK FastAPI server + the `/nudge` endpoint.
- **Firestore** — durable working memory (honest in-memory fallback).
- **Secret Manager** — the Gmail/Calendar OAuth token, kept out of the image.
- **Cloud Scheduler** — fires the daily proactive nudge.
- **Gmail API + Calendar API** — real action: draft, inbox search, read day, reminders.
- Python, Docker.

---

## Data sources

- **User's own working memory** (tasks, energy, preferences, learned notes) — stored in
  **Firestore**, owned by the user, written only through explicit tool calls.
- **The user's Gmail** — compose scope for drafts, read-only scope for inbox search.
  Never sends, deletes, or modifies.
- **The user's Google Calendar** — reads today's events, writes notifying reminders the
  user agreed to.
- **Grounded web search** (via ADK `google_search`) for real external facts (addresses,
  deadlines, procedures) instead of parametric guesses.
- All OAuth is ÍMPETU's own consented token, stored in Secret Manager — no secret is ever
  committed to the repo.

---

## Findings and learnings

- **Activation energy, not planning, is the real accessibility gap.** Framing every
  feature around "lower the energy to start" changed the product more than adding
  capabilities did.
- **Honest degradation earns trust.** Making every side-effecting tool report whether it
  actually happened (draft created / memory saved / reminder scheduled — or not) matters
  more for a neurodivergent user than a smooth-but-fake success.
- **Proactivity is the line between a chat box and a collaborator.** A purely reactive
  assistant is not enough for an ADHD brain; the daily Cloud Scheduler → /nudge → Calendar
  loop, running with the computer off, is what makes it a partner.
- **One voice, many agents.** Sub-agents improve reasoning, but the anti-redundancy rules
  (the mail is from the user's own address — no repeated name, one sign-off) were needed
  to keep the drafter from sounding robotic.
- **Grounding beats memory for facts.** Forcing a web lookup before stating any specific
  external fact removed a whole class of confident-but-wrong answers.

---

## ~4-minute demo video — script outline

Target ~4:00. Show the loop, the real side effects, and Google Cloud proof.

1. **(0:00–0:35) Problem.** "Starting is the hard problem, not planning." One line on
   executive dysfunction; why a wall-of-steps plan fails a stuck brain.
2. **(0:35–1:00) Value.** ÍMPETU lowers the energy to start: negotiates one step, does the
   scary 10%, remembers you, comes back on its own.
3. **(1:00–2:30) Live run** at the .run URL:
   - Say "I'm overwhelmed and can't start." → it offers one negotiated step + asks energy 1–5.
   - Pick a step → it **drafts a real email** → cut to Gmail showing the draft (visible state).
   - It **saves the memory** and **schedules a reminder** → show the Calendar event.
   - Show it recalling the task in a fresh session (long-term memory, no re-explaining).
4. **(2:30–3:20) Proactive loop + Google Cloud proof.** Show Cloud Scheduler job
   `impetu-nudge`, trigger `/nudge`, show the new Calendar reminder appear — computer-off
   proactivity. Show Cloud Run console + the .run URL as deployment proof.
5. **(3:20–4:00) Architecture + close.** `docs/architecture.svg` on screen; one line each
   on Vertex/Gemini, ADK, Firestore, the honest-degradation principle. Close on the thesis.

**Must be visible on camera:** draft created, memory saved, reminder scheduled, return
later, and clear Google Cloud deployment proof (console/logs/.run URL).
