import threading
import time

import httpx
import pytest

from acp_mesh.config import AcpMeshConfig
from acp_mesh.pending import PendingTaskStore
from acp_mesh.protocol import Peer, TaskEnvelope, new_task_id
from acp_mesh.server import PING_CAPABILITY, AcpMeshServer


@pytest.fixture()
def running_server(free_port):
    cfg = AcpMeshConfig(agent_id="hermes.test.agents.local", listen_port=free_port, capabilities=["hermes.echo"])
    server = AcpMeshServer(cfg, PendingTaskStore())
    server.start()
    try:
        yield server
    finally:
        server.stop()


def test_card_advertises_configured_and_ping_capability(running_server):
    card = running_server.card()
    assert "hermes.echo" in card.capabilities
    assert PING_CAPABILITY in card.capabilities


def test_ping_over_real_http(running_server):
    resp = httpx.post(
        f"{running_server.config.endpoint}/acp/task",
        json=TaskEnvelope(new_task_id(), PING_CAPABILITY, {}, 4, "tester", []).to_dict(),
        timeout=5,
    )
    data = resp.json()
    assert data["status"] == "ok"
    assert data["result"]["pong"] is True
    assert data["handled_by"] == "hermes.test.agents.local"


def test_well_known_card_endpoint(running_server):
    resp = httpx.get(f"{running_server.config.endpoint}/.well-known/acp.json", timeout=5)
    assert resp.status_code == 200
    assert resp.json()["agent_id"] == "hermes.test.agents.local"


def test_local_capability_blocks_until_resolved(running_server):
    task = TaskEnvelope(new_task_id(), "hermes.echo", {"say": "hi"}, 4, "tester", [])

    box = {}

    def send():
        box["resp"] = httpx.post(
            f"{running_server.config.endpoint}/acp/task", json=task.to_dict(), timeout=10
        ).json()

    t = threading.Thread(target=send)
    t.start()

    deadline = time.time() + 5
    pending = []
    while time.time() < deadline:
        pending = running_server.pending.list_pending()
        if pending:
            break
        time.sleep(0.02)
    assert len(pending) == 1
    assert pending[0].task.capability == "hermes.echo"

    running_server.pending.resolve(task.task_id, {
        "status": "ok", "result": {"echo": "hi"},
        "handled_by": running_server.config.agent_id, "trace": [running_server.config.agent_id],
    })
    t.join(timeout=5)
    assert box["resp"]["status"] == "ok"
    assert box["resp"]["result"]["echo"] == "hi"


def test_local_capability_times_out_if_never_answered(free_port):
    cfg = AcpMeshConfig(
        agent_id="hermes.test-timeout.agents.local", listen_port=free_port,
        capabilities=["hermes.echo"], pending_task_timeout_seconds=0.3,
    )
    server = AcpMeshServer(cfg, PendingTaskStore())
    server.start()
    try:
        resp = httpx.post(
            f"{cfg.endpoint}/acp/task",
            json=TaskEnvelope(new_task_id(), "hermes.echo", {}, 4, "tester", []).to_dict(),
            timeout=5,
        )
        assert resp.status_code == 504
        assert resp.json()["status"] == "error"
    finally:
        server.stop()


def test_loop_detection_rejects_task_already_in_trace(running_server):
    task = TaskEnvelope(new_task_id(), "hermes.echo", {}, 4, "tester", ["hermes.test.agents.local"])
    resp = httpx.post(f"{running_server.config.endpoint}/acp/task", json=task.to_dict(), timeout=5)
    assert resp.status_code == 409
    assert "loop" in resp.json()["error"]


def test_relay_forward_to_configured_peer(free_port, fake_peer):
    cfg = AcpMeshConfig(
        agent_id="hermes.relay.agents.local", listen_port=free_port,
        capabilities=[],  # no local capabilities -- must forward
        peers=[Peer("fake-peer.agents.test", fake_peer)],
    )
    server = AcpMeshServer(cfg, PendingTaskStore())
    server.start()
    try:
        task = TaskEnvelope(new_task_id(), "test.add", {"a": 20, "b": 22}, 4, "tester", [])
        resp = httpx.post(f"{cfg.endpoint}/acp/task", json=task.to_dict(), timeout=5)
        data = resp.json()
        assert data["status"] == "ok"
        assert data["result"]["sum"] == 42
        assert data["handled_by"] == "fake-peer.agents.test"
        assert data["trace"] == ["hermes.relay.agents.local", "fake-peer.agents.test"]
    finally:
        server.stop()


def test_no_route_when_capability_unknown_and_no_peers(running_server):
    task = TaskEnvelope(new_task_id(), "nobody.has.this", {}, 4, "tester", [])
    resp = httpx.post(f"{running_server.config.endpoint}/acp/task", json=task.to_dict(), timeout=5)
    assert resp.status_code == 404
    assert resp.json()["status"] == "error"
