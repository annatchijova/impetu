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

import hashlib
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


# A note is a fact the agent will later be told about this person. It is written
# by the MODEL, from material that may include email the person did not write, so
# it is capped and carries its provenance. See docs/RED-TEAM.md F7.
MAX_NOTE_VALUE = 500
MAX_NOTES = 24

SOURCE_USER = "user_stated"      # the person said it in their own words
SOURCE_MODEL = "model_inferred"  # the model concluded it
SOURCE_EXTERNAL = "external"     # derived from email / search results


def _new_id() -> str:
    # uuid4 is fine here: these ids are not part of any sealed/deterministic path.
    return uuid.uuid4().hex[:12]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable_id(*parts: str) -> str:
    """Deterministic id for a logical operation, so a retry converges."""
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:12]


def note_record(value: str, source: str = SOURCE_MODEL) -> dict:
    """Wrap a note so its origin survives into the prompt."""
    text = (value or "").strip()
    truncated = len(text) > MAX_NOTE_VALUE
    if truncated:
        text = text[: MAX_NOTE_VALUE - 1].rstrip() + "\u2026"
    return {"value": text, "source": source, "at": _now(), "truncated": truncated}


def note_value(entry) -> str:
    """Read a note written in either the current or the legacy plain-string shape."""
    if isinstance(entry, dict):
        return entry.get("value", "")
    return entry or ""


def note_source(entry) -> str:
    if isinstance(entry, dict):
        return entry.get("source", SOURCE_MODEL)
    return SOURCE_MODEL  # legacy notes have no recorded provenance


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


_SHARED: "Store | None" = None


def get_store() -> "Store":
    """The one Store this process uses.

    `tools` and `nudge` each used to construct their own, so against the
    in-memory fallback `/nudge` and `/api/state` read a different store than the
    agent's tools wrote to, and Firestore was health-checked twice at import.
    See docs/RED-TEAM.md F10.
    """
    global _SHARED
    if _SHARED is None:
        _SHARED = Store()
    return _SHARED


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
        # Derive the id from the content, not from uuid4(). A lost response
        # followed by a retry then rewrites the SAME document instead of creating
        # a second open task that can never be closed. See docs/RED-TEAM.md F5.
        task_id = _stable_id(user_id, (title or "").strip().casefold())
        existing = self._get(f"users/{user_id}/tasks/{task_id}")
        if existing and existing.get("status") != "done":
            res = StoreResult(ok=True, persisted=self.durable, data=existing)
            res.data = {"task_id": task_id, **existing}
            return res
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

    def remember(self, user_id: str, key: str, value: str,
                 source: str = SOURCE_MODEL, log: bool = True) -> StoreResult:
        """Store a durable note WITH its provenance, capped in size and count."""
        path = f"users/{user_id}"
        doc = self._get(path) or {"user_id": user_id, "notes": {}}
        notes = doc.setdefault("notes", {})
        notes[key] = note_record(value, source)
        self._evict_notes(notes)
        res = self._set(path, doc)
        if log:
            # Only describe what this call actually did. Inferring "Drafted
            # email" from a key prefix made the trail claim a side effect that
            # had not been attempted yet. See docs/RED-TEAM.md F6.
            label = "Set address preference" if key == "address" else f"Remembered: {key}"
            self.log_activity(user_id, "memory", label)
        return res

    @staticmethod
    def _evict_notes(notes: dict) -> None:
        """Keep the newest MAX_NOTES notes, so memory cannot grow without bound.

        Eviction is explicit and by age. Previously the prompt silently rendered
        whichever five notes dict ordering happened to surface.
        """
        if len(notes) <= MAX_NOTES:
            return
        protected = {k for k in notes if k == "address" or k.startswith("draft:")}
        ageing = [k for k in notes if k not in protected]
        ageing.sort(key=lambda k: (notes[k].get("at", "")
                                   if isinstance(notes[k], dict) else ""))
        for key in ageing[: max(0, len(notes) - MAX_NOTES)]:
            notes.pop(key, None)

    def recall_context(self, user_id: str) -> dict:
        profile = self._get(f"users/{user_id}") or {"user_id": user_id, "notes": {}}
        tasks = self._list(f"users/{user_id}/tasks")
        energy = self._list(f"users/{user_id}/energy")
        open_tasks = [t for t in tasks if t.get("status") != "done"]
        last_energy = energy[-1] if energy else None
        raw_notes = profile.get("notes", {})
        return {
            "durable": self.durable,
            "notes": {k: note_value(v) for k, v in raw_notes.items()},
            "note_sources": {k: note_source(v) for k, v in raw_notes.items()},
            "open_tasks": open_tasks,
            "last_energy": last_energy,
        }

    # --- outbound side effects -------------------------------------------
    def record_side_effect(self, user_id: str, kind: str, external_id: str,
                           status: str, detail: str = "") -> None:
        """Persist the identity of something we created OUTSIDE this system.

        Google hands back an event id and a draft id and ÍMPETU used to drop both
        on the floor, which is why it could not deduplicate, could not reconcile
        belief against reality, and could not verify its own activity trail. The
        document is keyed by the external id, so recording it twice is a no-op.
        See docs/RED-TEAM.md F9.
        """
        if not external_id:
            return
        try:
            self._set(f"users/{user_id}/side_effects/{external_id}", {
                "external_id": external_id,
                "kind": kind,
                "status": status,
                "detail": detail[:200],
                "at": _now(),
            })
        except Exception:  # noqa: BLE001 - never let bookkeeping break the action
            pass

    def pending_side_effects(self, user_id: str) -> list[dict]:
        """Side effects whose real-world outcome we never confirmed."""
        items = self._list(f"users/{user_id}/side_effects")
        return [i for i in items if i.get("status") == "unknown"]

    def resolve_side_effect(self, user_id: str, external_id: str, status: str,
                            resolved_id: str = "") -> None:
        """Record what we later learned about an UNKNOWN side effect."""
        path = f"users/{user_id}/side_effects/{external_id}"
        doc = self._get(path)
        if not doc:
            return
        doc["status"] = status
        doc["resolved_at"] = _now()
        if resolved_id and resolved_id != external_id:
            doc["external_id"] = resolved_id
        try:
            self._set(path, doc)
        except Exception:  # noqa: BLE001 - bookkeeping must never break a turn
            pass

    # --- activity trail --------------------------------------------------
    def log_activity(self, user_id: str, kind: str, summary: str,
                     status: str = "done") -> None:
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
                "status": status,
                "at": _now(),
            })
        except Exception:  # noqa: BLE001 - never let logging break a real action
            pass

    def recent_activity(self, user_id: str, limit: int = 8) -> list[dict]:
        """The most recent side effects, newest first."""
        items = self._list(f"users/{user_id}/activity")
        items.sort(key=lambda a: a.get("at", ""), reverse=True)
        return items[:limit]

    # --- prompt-facing view ----------------------------------------------
    def notes_for_prompt(self, user_id: str) -> list[dict]:
        """Notes as {key, value, source}, newest first, provenance intact."""
        profile = self._get(f"users/{user_id}") or {}
        out = []
        for key, entry in (profile.get("notes") or {}).items():
            if key == "address" or key.startswith("draft:"):
                continue
            out.append({"key": key, "value": note_value(entry),
                        "source": note_source(entry),
                        "at": entry.get("at", "") if isinstance(entry, dict) else ""})
        out.sort(key=lambda n: n["at"], reverse=True)
        return out
