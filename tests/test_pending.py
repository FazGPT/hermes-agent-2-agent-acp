import threading
import time

from acp_mesh.pending import PendingTaskStore
from acp_mesh.protocol import TaskEnvelope


def _task(task_id="t1"):
    return TaskEnvelope(task_id, "x.y", {"a": 1}, ttl=4, origin="a", trace=[])


def test_add_appears_in_pending():
    store = PendingTaskStore()
    store.add(_task())
    pending = store.list_pending()
    assert len(pending) == 1
    assert pending[0].task.task_id == "t1"


def test_resolve_wakes_waiter_with_result():
    store = PendingTaskStore()
    store.add(_task())

    results = {}

    def waiter():
        results["r"] = store.wait("t1", timeout_seconds=5)

    t = threading.Thread(target=waiter)
    t.start()
    # give the waiter a moment to actually start blocking
    time.sleep(0.1)
    ok = store.resolve("t1", {"status": "ok", "result": 42})
    t.join(timeout=5)

    assert ok is True
    assert results["r"] == {"status": "ok", "result": 42}
    # resolved tasks are popped -- no longer pending
    assert store.list_pending() == []


def test_resolve_unknown_task_returns_false():
    store = PendingTaskStore()
    assert store.resolve("nope", {"status": "ok"}) is False


def test_resolve_twice_second_call_fails():
    store = PendingTaskStore()
    store.add(_task())
    assert store.resolve("t1", {"status": "ok"}) is True
    assert store.resolve("t1", {"status": "ok"}) is False


def test_wait_times_out_without_resolution():
    store = PendingTaskStore()
    store.add(_task())
    result = store.wait("t1", timeout_seconds=0.2)
    assert result is None


def test_wait_unknown_task_returns_none_immediately():
    store = PendingTaskStore()
    start = time.monotonic()
    result = store.wait("nope", timeout_seconds=5)
    assert result is None
    assert time.monotonic() - start < 1  # didn't actually wait the full timeout


def test_discard_stale_removes_old_unresolved_only():
    store = PendingTaskStore()
    store.add(_task("old"))
    store.add(_task("new"))
    # Backdate the "old" entry
    with store._lock:
        store._tasks["old"].received_at = time.time() - 1000
    store.discard_stale(max_age_seconds=10)
    remaining = {p.task.task_id for p in store.list_pending()}
    assert remaining == {"new"}
