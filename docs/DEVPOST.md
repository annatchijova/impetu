# ÍMPETU — Devpost submission

Copy for the Devpost form (English, repo language). Paste each section into the
matching field; edit freely.

- **Category:** Collaborative Partner
- **Project URL (hosted):** https://impetu-brkvglmi2a-uc.a.run.app
- **Repository:** https://github.com/annatchijova/impetu
- **Architecture diagram:** `docs/architecture.svg` (upload this)
- **Demo video:** [paste your YouTube link]

---

## Elevator pitch (one line)

For a brain where *starting* is the hard part — not planning — ÍMPETU does the scary
ten percent, drops the real draft in your inbox one tap from sent, and comes back the
next day on its own. It walks you to the send button, and no further, because that
last step is yours.

---

## Inspiration — the problem no planner solves

Every productivity tool ever built assumes the bottleneck is knowing *what* to do. For
an autistic or ADHD brain, that assumption is exactly backwards. The plan is one
sentence. You can see it perfectly. And you still cannot begin.

The tasks that trap an executive-dysfunction brain are rarely trivial ones. They are
the message you have avoided for a year because it carries shame — telling a doctor you
stopped treatment, admitting you couldn't pay, asking for the help you need. Every day
you don't send it, the wall gets higher, and the not-doing becomes its own second
problem on top of the first.

So the answer is not another list. A list is the last thing a stuck brain can act on.
The gap isn't knowledge — it's the **activation energy to take the first step.**

ÍMPETU is built on one thesis: **starting is the hard problem, not planning.** Every
part of it exists to lower the energy to begin — and to stay beside the person on the
concrete next step, instead of handing them a plan and walking away, or deflecting them
to a hotline when it gets heavy.

---

## What it actually does

You tell ÍMPETU you're overwhelmed and can't start. It doesn't dump a plan and it
doesn't lecture. It offers **one** small next step — and then it does the part that
costs the most: it writes the actual message, in your voice, short and honest, and
**drops it straight into your Gmail as a real draft.** Not "you should email them." The
words now exist, sitting in your inbox, one tap from sent.

It reads your calendar to keep the ask realistic and places a gentle reminder for a
time you agreed to. It searches your own inbox when you've lost an address. It remembers
you between sessions — your open tasks, your energy, how you like to be addressed — so
you never re-explain. And the next day, running in Google Cloud with your computer
switched off, it reaches out to you first.

Two things it will never do. **It never sends for you** — pressing send is always
yours, because that last act, and its dignity, belongs to the person. And **it never
fakes a side effect:** if the draft was created, it says so; if it wasn't, it says that
too. It keeps you company on the next step; it never pushes a struggling person off to
a helpline.

---

## Features and functionality

- **One step at a time, negotiated.** It offers the next micro-step; you can change it
  or say no. Never a wall of steps, never an order — some autistic people shut down when
  told what to do. It speaks to you like a capable adult; no baby-talk, no infantilizing.
- **Does the scary 10%.** It drafts the real email in your voice — short, no repeated
  name — and leaves it as a **real Gmail draft**. You just review and send.
- **WhatsApp, one tap.** For the channel most people actually use, it builds a
  ready-to-send `wa.me` link with the message pre-written — you pick the contact and
  press send. No WhatsApp Business API; the same boundary holds — it never sends.
- **Long-term memory across sessions.** Open tasks, last energy level, what framing
  works for you, how you like to be addressed (él / ella / elle) — so you never
  re-explain. Backed by Firestore, with an honest in-memory fallback.
- **Looks up what you don't know.** When a real fact is missing (an address, a deadline,
  a procedure) it uses grounded web search instead of inventing it — and says so if it
  can't find it.
- **Finds it in your inbox.** Read-only Gmail search to answer "what was that address?"
  — it never sends, deletes, or changes anything.
- **Reads your day and schedules.** Checks today's calendar to keep the ask realistic,
  and creates reminders that actually reach you (popup + email, on time).
- **Comes to you.** A daily Cloud Scheduler job turns your open task into an active
  reminder and reaches out first — no app open, computer off. A purely reactive
  assistant is not enough for an ADHD brain.
- **A team behind one voice.** Specialized sub-agents (a decomposer, a drafter) work in
  the background; you always talk to a single, coherent voice.
- **Honest degradation.** Every tool with a side effect reports whether it actually
  happened — it never fakes success.

---

## The boundary that makes it trustworthy

ÍMPETU acts on your real accounts — it drafts, it schedules, it reaches out. What makes
that safe is not a promise; it's the architecture. The model can propose and it can act,
but two lines are drawn in code, not in prose: it cannot send, and it cannot report a
side effect it did not verify. A neurodivergent user has usually been let down by
confident, smooth systems that were quietly wrong. So ÍMPETU is built to be honest
before it is impressive — the restraint *is* the feature.

---

## Technologies used

- **Gemini 3.5 (Vertex AI)** — the reasoning; it picks the action (the LLM is in the
  decision path by design).
- **Google Agent Development Kit (ADK)** — `LlmAgent`, function tools, `AgentTool`
  sub-agents, `google_search` grounding.
- **Cloud Run** — hosts the ADK FastAPI server, the landing page, and the `/nudge`
  endpoint that powers the proactive loop.
- **Firestore** — durable working memory (with an honest in-memory fallback).
- **Secret Manager** — the Gmail/Calendar OAuth token, kept out of the image and the repo.
- **Cloud Scheduler** — fires the daily proactive nudge.
- **Gmail API + Calendar API** — real action: draft, inbox search, read the day, reminders.
- Python, Docker.

---

## Data sources

- **Your own working memory** (tasks, energy, preferences, learned notes) — stored in
  **Firestore**, owned by you, written only through explicit tool calls.
- **Your Gmail** — compose scope for drafts, read-only scope for inbox search. It never
  sends, deletes, or modifies.
- **Your Google Calendar** — reads today's events, writes only the reminders you agreed to.
- **Grounded web search** (via ADK `google_search`) for real external facts — addresses,
  deadlines, procedures — instead of parametric guesses.
- All OAuth runs on a consented token held in Secret Manager. No secret is ever committed
  to the repo.

---

## Findings and learnings

- **Activation energy, not planning, is the real accessibility gap.** Reframing every
  feature around "lower the energy to start" changed the product far more than any
  individual capability did. It is also what separates ÍMPETU from a to-do app.
- **Doing the last-but-one step is the whole game.** The value isn't the plan or even
  the draft text — it's that the finished words land one tap from sent, in the real
  place they need to go. That is the difference between "I know what to write" and a
  message that actually leaves.
- **Honesty beats smoothness for a neurodivergent user.** Making every side-effecting
  tool report whether it *actually* happened — draft created, reminder scheduled, or not
  — earns more trust than a polished success that might be fake.
- **Proactivity is the line between a chat box and a collaborator.** A reactive assistant
  isn't enough for an ADHD brain; the daily Cloud Scheduler → /nudge → Calendar loop,
  running with the computer off, is what makes it a partner rather than a tool you have
  to remember to open.
- **Grounding beats memory for facts.** Forcing a web lookup before stating any specific
  external fact removed a whole class of confident-but-wrong answers.
- **The channel matters as much as the message.** In much of the world real messages go
  over WhatsApp, not email — so "does the scary 10%" had to reach that channel too, which
  is why the one-tap `wa.me` link exists.

---

## Honest limitations (by design)

- It **drafts; you send.** Every channel stops at the send button on purpose.
- WhatsApp is a **pre-filled link**, not an automated send (that boundary is deliberate,
  not a gap to close).
- The public demo is pinned to a safe demo profile and does not touch a real Gmail or
  Calendar — the real side effects run on a connected, consented account.
- It is a companion, **not medical or legal advice**, and it says so; it stays on the
  concrete next step rather than pretending to be a therapist.

A named limitation is worth more than a hidden one. Honest scope is the point.
