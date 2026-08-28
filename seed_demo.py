# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Anna Tchijova
"""Seed a public DEMO profile so the landing action center has something real to
show — an open task, its next step, and a short activity trail — without ever
exposing a real user's data.

Idempotent: seeds the task only if there is no open one, and the activity trail
only if it is empty. Safe to run against the live Firestore (uses
GOOGLE_CLOUD_PROJECT / ADC like the app).

    python3 seed_demo.py
"""
from __future__ import annotations

import os

from agent.state import Store

# Must match server.main._DEMO_USER so the seeded profile is the one the public
# demo (and the ADK dev-ui, which uses "user") actually reads and writes.
DEMO_USER = os.environ.get("IMPETU_DEMO_USER", "user")

# Newest last: recent_activity() returns newest-first, so a judge reads the most
# recent move at the top. This mirrors one real session's side effects.
_TRAIL = [
    ("energy", "Logged energy 2/5"),
    ("task", "Saved task: Renew my driver's licence"),
    ("step", "Negotiated next step: Open the booking site and pick the nearest office"),
    ("memory", "Set address preference"),
    ("memory", "Drafted email: booking confirmation"),
]


def seed() -> None:
    store = Store()
    if not store.durable:
        print("WARNING: Firestore not reachable — seeding the in-memory store only "
              "(will not survive). Set GOOGLE_CLOUD_PROJECT + ADC to seed the real "
              "backend.")

    ctx = store.recall_context(DEMO_USER)
    if ctx.get("open_tasks"):
        print(f"demo already has {len(ctx['open_tasks'])} open task(s); skipping task seed.")
    else:
        task = store.save_task(
            DEMO_USER,
            "Renew my driver's licence",
            "I have to renew my licence — I gathered the papers but never booked the slot.",
        )
        tid = task.data["task_id"]
        store.save_next_step(
            DEMO_USER, tid,
            "Open the booking site and pick the nearest office", "small")
        store.log_energy(DEMO_USER, 2, "tired but want this off my plate")
        print(f"seeded demo task {tid} (persisted={task.persisted})")

    if store.recent_activity(DEMO_USER):
        print("demo already has an activity trail; skipping.")
    else:
        for kind, summary in _TRAIL:
            store.log_activity(DEMO_USER, kind, summary)
        print(f"seeded demo activity trail ({len(_TRAIL)} entries)")


if __name__ == "__main__":
    seed()
