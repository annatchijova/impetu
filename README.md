# ÍMPETU

A calm, collaborative agent for autistic and ADHD minds. Its whole design rests on
one thesis:

> **Starting is the hard problem, not planning.**

For an executive-dysfunction brain the plan is never the bottleneck; the activation
energy to *begin* is. Every part of ÍMPETU exists to lower that energy.

Built for the **All Things Agentic** hackathon (Collaborative Partner track).

## What it does

- **One atomic step at a time.** Never a wall of steps. If you hesitate, the step was
  too big, so it splits again, smaller.
- **Negotiates, never commands.** It offers and asks; you can always say no or pick
  another step. This is deliberate: some autistic people shut down when told what to
  do (demand avoidance).
- **Does the scary 10% for you.** It drafts the email, writes the template, opens the
  thing with a first ugly line already in it. You edit; you don't face a blank page.
- **Reads and adapts to your energy.** Low battery means a tinier step, or explicit
  permission to rest with zero guilt.
- **Holds your working memory.** It remembers where you were and how you felt, so you
  don't have to carry it between sessions.
- **Adapts to you.** It learns how you want to be addressed (él / ella / elle) and
  what kind of framing lands for you.
- **No shame, ever, and it stays present** — it does not hand a struggling person off
  to a hotline; it helps them take the next small, real step.

## Architecture

- **Agent framework:** Google ADK (`LlmAgent` + function tools).
- **Model:** Gemini 3.5 (`MODEL` env var, default `gemini-3.5-flash`).
- **State:** Firestore for durable "externalized working memory", with an honest
  in-memory fallback that never pretends a write persisted.

```
agent/
  prompts.py   the 8 co-regulation rules (the soul)
  tools.py     real-action tools; each reports whether state actually persisted
  state.py     Firestore-backed working memory + honest fallback
  agent.py     the LlmAgent; dynamic instruction injects your address preference
try_it.py      local runner
```

## Run it locally

Requires a `GEMINI_API_KEY` in your environment.

```bash
pip install -r requirements.txt
python3 try_it.py "whatever you've been putting off"
```

## License

Apache License 2.0 — see [LICENSE](LICENSE). Copyright 2026 Anna Tchijova.
