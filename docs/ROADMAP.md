# ÍMPETU — Roadmap

Externalized so we don't have to hold it in our heads (on brand).

- **Today:** 2026-08-19
- **Submission deadline:** 2026-08-31, 5:00pm PDT (~12 days)
- **Hackathon:** All Things Agentic — Collaborative Partner track
- **Judging:** Innovation & Operational Utility 40% / Architecture 30% / Demo 30%

Each item lists: **why** (tie to the thesis), **how** (ADK/GCP pieces, all present in
ADK 2.1.0 unless noted), and **done when** (an honest, testable acceptance check).

Legend: `[x]` done · `[ ]` todo · `(S/M/L)` effort.

---

## Phase 0 — Foundations  ✅ DONE

- [x] ADK `LlmAgent` on Gemini 3.5, 9 tools, verified end-to-end against `gemini-3.5-flash`.
- [x] Co-regulation prompt (8 rules) + hard no-crisis-hotline boundary.
- [x] Externalized working memory (`state.py`) with **honest degradation** (`persisted` flag).
- [x] Address preference (él/ella/elle) captured + injected into the prompt each turn.
- [x] Apache-2.0 license, SPDX headers, README, private GitHub repo `annatchijova/impetu`.

---

## Phase 1 — Core loop & real state

- [ ] **1a. Native negotiation with `get_user_choice`** (S)
  - *Why:* rule 3 (negotiate, never command) becomes a real structured choice, not
    free text the user has to parse.
  - *How:* add ADK's `get_user_choice` tool; instruct the agent to offer 2-3 micro-steps
    through it whenever it proposes a next step.
  - *Done when:* a turn proposing steps surfaces them as discrete choices and the pick
    is recorded as the saved next step.

- [x] **1b. Long-term memory across sessions** (M) — DONE (v1, Firestore-backed)
  - *Why:* the heart of "externalize working memory" — ÍMPETU should remember you over
    weeks (patterns, what worked, your open projects), not just within one session.
  - *How (shipped):* the dynamic instruction injects the user's recalled state (address,
    last energy, open threads + next step, learned notes) from the existing `Store` into
    the prompt every turn, so the agent greets from where they left off.
  - *Done:* verified by a two-session test — energy 2/5 + "renovar el monotributo" + the
    agreed next step ("abrir la pestaña de AFIP") were recalled in a fresh session with
    no re-explaining.
  - *Later upgrade (1b-v2):* `vertex_ai_memory_bank_service` for semantic recall across
    many sessions, once GCP is provisioned (Phase 5b).

- [x] **1c. Live Firestore persistence** (S) — DONE
  - *Why:* stop running on the in-memory fallback; real durable state = the Architecture 30%.
  - *How (shipped):* the `(default)` Firestore database already existed on `vigia-497422`
    (nam5, native). Installed `google-cloud-firestore` into the user site and dropped
    `IMPETU_FORCE_MEMORY`; the Store connects via ADC.
  - *Done:* a task saved in one Store was read back by a fresh Store (`durable=True`), and
    an end-to-end turn through the `adk web` server persisted `address='ella'` + the task
    "Renovar el DNI" into real Firestore (verified, then cleaned up).

---

## Phase 2 — Real-world action (the "scary 10%" made real)

- [x] **2a. Grounded unsticking with search** (S) — DONE
  - *Why:* turns "I don't even know the steps" into concrete ones — the agent looks up
    the real answer instead of guessing (the exact failure that surfaced when it invented
    Defensoria email addresses from memory).
  - *How (shipped):* added ADK's `google_search` to the agent (mixes fine with the
    function tools in ADK 2.1). Prompt rule 9 forces search before stating any specific
    external fact (address, deadline, procedure) - do not trust parametric memory.
  - *Done:* verified via grounding_metadata — a lookup produced real `web_search_queries`
    instead of a remembered guess.

- [x] **2b. Real Gmail draft creation** (M) — DONE
  - *Why:* the strongest demo moment — the draft actually appears in your Gmail; opening
    it is one click, not a blank page.
  - *How (shipped):* `agent/gmail.py` uses the Gmail API with ÍMPETU's own OAuth
    (gmail.compose scope, never sends). `setup_gmail.py` runs a one-time InstalledApp
    flow (fixed loopback port, unbuffered, no auto-open) to write `gmail_token.json`.
    `draft_email` creates a real draft when connected and degrades honestly otherwise.
  - *Done:* verified end-to-end — `create_draft` returned `created=True` with a draft id
    and `drafts.list` confirmed it in the account. Sending stays a human action.

- [ ] **2c. Calendar read + write** (M)
  - *Why:* know what's realistic *today* (read the day), and externalize time by placing
    a gentle, movable reminder — not a nag.
  - *How:* Google Calendar API (same OAuth). Read today's load; create tentative events.
  - *Done when:* ÍMPETU can say "you already have 3 things today, want the tiniest step?"
    and can place a reminder the user approved.

---

## Phase 3 — Orchestration & presence

- [x] **3a. Multi-agent team** (M) — DONE
  - *Why:* cleaner reasoning — a decomposer that splits, a drafter that writes the 10% -
    without splitting the single user-facing voice.
  - *How (shipped):* two background sub-agents (`decomposer`, `drafter`) wired into the
    root via `AgentTool`. The root stays the only voice the user sees; it MUST delegate
    any draft to `drafter`, which carries the anti-redundancy rules (the mail is from the
    user's own address, so no repeated name, no "Mi nombre es X", one sign-off).
  - *Done:* verified — the root delegated to `drafter`, the draft came back clean (topic
    subject, single signature), and it composed with google_search grounding a real
    address. No tone regression; fixed the "name 4x" and feelings-narration issues.

- [ ] **3b. Proactive gentle nudges** (M)
  - *Why:* externalize time — ÍMPETU reaches out at a chosen moment ("want to keep going
    with the papers?"), always skippable, never guilt-tripping.
  - *How:* Cloud Scheduler → Cloud Run endpoint that runs a check-in turn; opt-in, with a
    hard rule against nagging.
  - *Done when:* a scheduled, user-approved nudge fires once and is trivially dismissable.

---

## Phase 4 — Multimodal (ambitious / stretch)

- [ ] **4a. Voice / live body-double** (L)
  - *Why:* accessibility — talk instead of type when typing is the wall.
  - *How:* ADK live (`LiveRequestQueue`) + a Gemini native-audio model (confirm access on
    the key first).
  - *Done when:* a spoken sentence gets a spoken, in-character reply through the loop.

- [ ] **4b. Computer use — fill the form for you** (L, delicate)
  - *Why:* the ultimate activation-energy kill: the agent operates the browser and does
    the task, with the user in the loop.
  - *How:* ADK `computer_use` tool, tightly scoped, confirm-before-act.
  - *Done when:* it completes one real, safe form end-to-end with explicit per-step consent.
  - *Guardrail:* only if Phases 1-3 are solid; never at the cost of the core.

---

## Phase 5 — Ship (non-negotiable for submission)

- [ ] **5a. Chat UI** (M) — a simple web chat to record the demo against.
- [ ] **5b. Deploy to Cloud Run + live Firestore + secrets** (M) — the hosted URL the
      hackathon requires; `GEMINI_API_KEY` via Secret Manager, not baked in.
- [ ] **5c. Architecture diagram + README polish** (S) — required submission artifact.
- [ ] **5d. ~4-min demo video + Devpost submission** (M) — problem, value, live run,
      Google Cloud proof; category selected; repo shared with required emails.

---

## Sequencing logic

Value-per-effort and thesis-fidelity first: **1b (long-term memory)** and **1a/2a**
(cheap, deepen the core) → **2b/2c** (real action, best demo) → **3a/3b** (presence) →
**Phase 5** interleaved from ~D8 so shipping is never rushed → **Phase 4** only if time
allows. Ship beats scope: a solid Phases 1-2 + a great video wins more than a fragile
everything.

## Guardrails that never move

- LLM may drive *action* (agentic), but the **no-shame** and **no-hotline-handoff**
  boundaries are hard constraints in every phase.
- Every new tool reports honestly whether its side effect actually happened.
- No secret ever committed to the repo.
