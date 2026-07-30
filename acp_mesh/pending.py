"""
Hand-off point between the inbound HTTP listener (server.py, running on a
background daemon thread) and the model's own tool-calling turn (tools.py,
running on whatever thread is executing that turn).

Why this exists instead of driving the model directly from the listener
thread: launching a subagent or injecting a message requires an active
Hermes turn context (see agent.subagent_lifecycle.bind_subagent_parent,
which is scoped only around a live turn in run_agent.py, and
PluginContext.inject_message, which is explicitly unavailable outside an
interactive CLI session). The listener thread has neither. So instead of
reaching into agent internals from a background thread, an incoming task
that Hermes can't satisfy by forwarding is parked here; a tool call
(acp_pending_tasks / acp_respond_task / acp_reject_task) made during a real
turn -- in the correct thread, with the correct context -- picks it up and
resolves it. The HTTP handler just blocks on the resulting Event.

This also means an incoming ACP task can only get a real answer while a
Hermes CLI session is actively running and the model chooses to act on it.
That's a deliberate trust boundary, not an oversight: ACP v0.1 has no
authentication (see ACP.md section 7), so a network peer's request is
just an unauthenticated string until a human's own agent decides to act on
it -- it never runs with tool access on its own.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .protocol import TaskEnvelope


@dataclass
class PendingTask:
    task: TaskEnvelope
    received_at: float
    event: threading.Event = field(default_factory=threading.Event)
    result: Optional[dict] = None  # {"status": "ok"|"error", ...}


class PendingTaskStore:
    """Thread-safe. One instance lives for the plugin's process lifetime."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tasks: Dict[str, PendingTask] = {}

    def add(self, task: TaskEnvelope) -> PendingTask:
        entry = PendingTask(task=task, received_at=time.time())
        with self._lock:
            self._tasks[task.task_id] = entry
        return entry

    def list_pending(self) -> List[PendingTask]:
        with self._lock:
            return [t for t in self._tasks.values() if t.result is None]

    def get(self, task_id: str) -> Optional[PendingTask]:
        with self._lock:
            return self._tasks.get(task_id)

    def resolve(self, task_id: str, result: dict) -> bool:
        """Fulfil or reject a pending task, waking up the blocked HTTP handler.

        Returns False if task_id is unknown or already resolved.
        """
        with self._lock:
            entry = self._tasks.get(task_id)
            if entry is None or entry.result is not None:
                return False
            entry.result = result
        entry.event.set()
        return True

    def wait(self, task_id: str, timeout_seconds: float) -> Optional[dict]:
        """Block (the HTTP handler thread) until resolved or timed out."""
        entry = self.get(task_id)
        if entry is None:
            return None
        entry.event.wait(timeout=timeout_seconds)
        with self._lock:
            self._tasks.pop(task_id, None)
        return entry.result

    def discard_stale(self, max_age_seconds: float) -> None:
        """Drop pending tasks nobody answered in time. The HTTP handler's own
        wait() timeout already returns a TTL-exhausted response to the caller
        independently -- this just prevents the dict from growing unbounded
        if a handler thread ever exits early."""
        cutoff = time.time() - max_age_seconds
        with self._lock:
            stale = [tid for tid, t in self._tasks.items()
                     if t.result is None and t.received_at < cutoff]
            for tid in stale:
                del self._tasks[tid]
