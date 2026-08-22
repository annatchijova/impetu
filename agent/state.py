# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Anna Tchijova
"""Externalized working memory: the durable domain state.

Source of truth is Firestore (serverless, pairs with Cloud Run). If Firestore is
unavailable (e.g. local dev with no credentials), we fall back to an in-process
store AND say so honestly - a caller must be able to tell "persisted" from "held
only in memory for this run". We never silently pretend a write survived.

Collections:
  users/{user_id}                      profile, preferences, learned notes
  users/{user_id}/tasks/{task_id}      one overwhelming thing, broken down
  users/{user_id}/energy/{entry_id}    energy log over time
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


def _new_id() -> str:
    # uuid4 is fine here: these ids are not part of any sealed/deterministic path.
    return uuid.uuid4().hex[:12]


@dataclass
class StoreResult:
    """Return type that never hides whether the write actually persisted."""
    ok: bool
    persisted: bool          # True only if it reached Firestore
    data: Any = None
    warning: Optional[str] = None


class _MemoryBackend:
    """Fallback store. Explicitly NOT durable across process restarts."""

    def __init__(self) -> None:
        self._db: dict[str, dict[str, Any]] = {}

    def doc_set(self, path: str, value: dict) -> None:
        self._db[path] = value

    def doc_get(self, path: str) -> Optional[dict]:
        return self._db.get(path)

    def collection(self, prefix: str) -> list[dict]:
        return [v for k, v in self._db.items() if k.startswith(prefix + "/")]


class Store:
    """Thin repository over Firestore with an honest in-memory fallback."""

    def __init__(self) -> None:
        self._persisted = False
        self._fs = None
        self._mem = _MemoryBackend()
        self._try_firestore()

    def _try_firestore(self) -> None:
        if os.environ.get("IMPETU_FORCE_MEMORY") == "1":
            return
        try:
            from google.cloud import firestore  # type: ignore

            project = os.environ.get("GOOGLE_CLOUD_PROJECT")
            self._fs = firestore.Client(project=project) if project else firestore.Client()
            # Touch a metadata doc so a missing/denied backend fails here, loudly,
            # rather than on the first real user write.
            self._fs.collection("_impetu_meta").document("healthcheck").set(
                {"ok": True}, merge=True
            )
            self._persisted = True
        except Exception as exc:  # noqa: BLE001 - degrade honestly, do not crash
            self._fs = None
            self._persisted = False
            self._boot_warning = f"Firestore unavailable, using in-memory store: {exc}"

    @property
    def durable(self) -> bool:
        return self._persisted

    # --- generic doc ops -------------------------------------------------
    def _set(self, path: str, value: dict) -> StoreResult:
        if self._fs is not None:
            self._fs.document(path).set(value, merge=True)
            return StoreResult(ok=True, persisted=True, data=value)
        self._mem.doc_set(path, value)
        return StoreResult(
            ok=True,
            persisted=False,
            data=value,
            warning="State held in memory only for this run - not persisted.",
        )

    def _get(self, path: str) -> Optional[dict]:
        if self._fs is not None:
            snap = self._fs.document(path).get()
            return snap.to_dict() if snap.exists else None
        return self._mem.doc_get(path)

    def _list(self, collection_path: str) -> list[dict]:
        if self._fs is not None:
            return [d.to_dict() for d in self._fs.collection(collection_path).stream()]
        return self._mem.collection(collection_path)

    # --- domain ops ------------------------------------------------------
    def save_task(self, user_id: str, title: str, raw_dump: str) -> StoreResult:
        task_id = _new_id()
        path = f"users/{user_id}/tasks/{task_id}"
        doc = {
            "task_id": task_id,
            "title": title,
            "raw_dump": raw_dump,
            "status": "open",
            "steps": [],
        }
        res = self._set(path, doc)
        res.data = {"task_id": task_id, **doc}
        self.log_activity(user_id, "task", f"Saved task: {title}")
        return res

    def save_next_step(self, user_id: str, task_id: str, step_text: str, size: str) -> StoreResult:
        path = f"users/{user_id}/tasks/{task_id}"
        doc = self._get(path) or {"task_id": task_id, "steps": [], "status": "open"}
        step = {"step_id": _new_id(), "text": step_text, "size": size, "done": False}
        doc.setdefault("steps", []).append(step)
        res = self._set(path, doc)
        res.data = step
        self.log_activity(user_id, "step", f"Negotiated next step: {step_text}")
        return res

    def mark_step_done(self, user_id: str, task_id: str, step_id: str) -> StoreResult:
        path = f"users/{user_id}/tasks/{task_id}"
        doc = self._get(path)
        if not doc:
            return StoreResult(ok=False, persisted=self.durable, warning="Task not found.")
        for s in doc.get("steps", []):
            if s.get("step_id") == step_id:
                s["done"] = True
        if doc.get("steps") and all(s.get("done") for s in doc["steps"]):
            doc["status"] = "done"
        res = self._set(path, doc)
        self.log_activity(user_id, "done", "Marked a step done")
        return res

    def log_energy(self, user_id: str, level: int, note: str = "") -> StoreResult:
        entry_id = _new_id()
        path = f"users/{user_id}/energy/{entry_id}"
        res = self._set(path, {"entry_id": entry_id, "level": level, "note": note})
        self.log_activity(user_id, "energy", f"Logged energy {level}/5")
        return res

    def remember(self, user_id: str, key: str, value: str) -> StoreResult:
        path = f"users/{user_id}"
        doc = self._get(path) or {"user_id": user_id, "notes": {}}
        doc.setdefault("notes", {})[key] = value
        res = self._set(path, doc)
        if key.startswith("draft:"):
            summ = f"Drafted email: {key[6:]}"
        elif key == "address":
            summ = "Set address preference"
        elif key.startswith("worked:"):
            summ = "Noted what worked"
        else:
            summ = f"Remembered: {key}"
        self.log_activity(user_id, "memory", summ)
        return res

    def recall_context(self, user_id: str) -> dict:
        profile = self._get(f"users/{user_id}") or {"user_id": user_id, "notes": {}}
        tasks = self._list(f"users/{user_id}/tasks")
        energy = self._list(f"users/{user_id}/energy")
        open_tasks = [t for t in tasks if t.get("status") != "done"]
        last_energy = energy[-1] if energy else None
        return {
            "durable": self.durable,
            "notes": profile.get("notes", {}),
            "open_tasks": open_tasks,
            "last_energy": last_energy,
        }

    # --- activity trail --------------------------------------------------
    def log_activity(self, user_id: str, kind: str, summary: str) -> None:
        """Append one visible side effect to the person's activity trail, so the
        agent's real actions can be shown, not just described.

        Best-effort by design: a logging failure must never break the operation
        that produced the side effect, so everything here is swallowed.
        """
        try:
            aid = _new_id()
            self._set(f"users/{user_id}/activity/{aid}", {
                "id": aid,
                "kind": kind,
                "summary": summary[:140],
                "at": datetime.now(timezone.utc).isoformat(),
            })
        except Exception:  # noqa: BLE001 - never let logging break a real action
            pass

    def recent_activity(self, user_id: str, limit: int = 8) -> list[dict]:
        """The most recent side effects, newest first."""
        items = self._list(f"users/{user_id}/activity")
        items.sort(key=lambda a: a.get("at", ""), reverse=True)
        return items[:limit]
