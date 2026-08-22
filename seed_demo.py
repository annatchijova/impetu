# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Anna Tchijova
"""Seed a public DEMO profile so the landing action center has something real to
show — an open task and its next step — without ever exposing a real user's data.

Idempotent: it seeds only if the demo user has no open task yet. Safe to run
against the live Firestore (uses GOOGLE_CLOUD_PROJECT / ADC like the app).

    python3 seed_demo.py
"""
from __future__ import annotations

from agent.state import Store

DEMO_USER = "demo"


def seed() -> None:
    store = Store()
    ctx = store.recall_context(DEMO_USER)
    if not store.durable:
        print("WARNING: Firestore not reachable — seeding the in-memory store only "
              "(this will not survive). Set GOOGLE_CLOUD_PROJECT + ADC to seed the "
              "real backend.")
    if ctx.get("open_tasks"):
        print(f"demo already has {len(ctx['open_tasks'])} open task(s); nothing to do.")
        return

    task = store.save_task(
        DEMO_USER,
        "Renew my driver's licence",
        "I have to renew my licence — I gathered the papers but never booked the slot.",
    )
    tid = task.data["task_id"]
    store.save_next_step(
        DEMO_USER, tid,
        "Open the booking site and pick the nearest office",
        "small",
    )
    store.log_energy(DEMO_USER, 2, "tired but want this off my plate")
    print(f"seeded demo task {tid} (persisted={task.persisted})")


if __name__ == "__main__":
    seed()
