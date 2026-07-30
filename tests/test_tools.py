import json

import pytest

import acp_mesh.tools as acp_tools
from acp_mesh import state
from acp_mesh.config import AcpMeshConfig
from acp_mesh.pending import PendingTaskStore
from acp_mesh.protocol import TaskEnvelope, new_task_id
from acp_mesh.server import AcpMeshServer


@pytest.fixture(autouse=True)
def _reset_state():
    yield
    state.set_server(None)


def test_tool_defs_shape_matches_hermes_registry_register_signature():
    """Every entry must be a valid kwargs dict for tools.registry.register()
    (name, toolset, schema, handler, ...) -- see __init__.py's register(ctx),
    which calls ctx.register_tool(**tool_def) for each of these."""
    names = set()
    for tdef in acp_tools.TOOL_DEFS:
        assert set(tdef) <= {
            "name", "toolset", "schema", "handler", "check_fn",
            "requires_env", "is_async", "description", "emoji", "override",
        }
        assert tdef["toolset"] == "acp_mesh"
        assert tdef["schema"]["name"] == tdef["name"]
        assert "description" in tdef["schema"]
        assert "parameters" in tdef["schema"]
        names.add(tdef["name"])
    assert names == {
        "acp_resolve", "acp_card", "acp_send_task",
        "acp_pending_tasks", "acp_respond_task", "acp_reject_task",
    }


@pytest.mark.asyncio
async def test_acp_resolve_handler(monkeypatch, fake_registry):
    monkeypatch.setattr(
        acp_tools, "load_acp_mesh_config",
        lambda: AcpMeshConfig(agent_id="a", registry_url=fake_registry),
    )
    out = await acp_tools._acp_resolve("test.add")
    data = json.loads(out)
    assert data["agents"] == []  # nobody registered yet, but no error either


@pytest.mark.asyncio
async def test_acp_resolve_without_registry_configured_is_a_tool_error(monkeypatch):
    monkeypatch.setattr(
        acp_tools, "load_acp_mesh_config", lambda: AcpMeshConfig(agent_id="a"),
    )
    out = await acp_tools._acp_resolve("x.y")
    assert "error" in json.loads(out)


@pytest.mark.asyncio
async def test_acp_send_task_handler_direct_endpoint(fake_peer):
    out = await acp_tools._acp_send_task("test.add", {"a": 2, "b": 2}, fake_peer, 4)
    data = json.loads(out)
    assert data["status"] == "ok"
    assert data["result"]["sum"] == 4


def test_acp_pending_tasks_without_running_server_is_a_tool_error():
    out = acp_tools._acp_pending_tasks()
    assert "error" in json.loads(out)


def test_pending_tasks_respond_and_reject_round_trip(free_port):
    cfg = AcpMeshConfig(agent_id="hermes.tool-test.agents.local", listen_port=free_port, capabilities=["hermes.echo"])
    server = AcpMeshServer(cfg, PendingTaskStore())
    server.start()
    state.set_server(server)
    try:
        t1 = TaskEnvelope(new_task_id(), "hermes.echo", {"say": "a"}, 4, "origin1", [])
        t2 = TaskEnvelope(new_task_id(), "hermes.echo", {"say": "b"}, 4, "origin2", [])
        server.pending.add(t1)
        server.pending.add(t2)

        listed = json.loads(acp_tools._acp_pending_tasks())
        assert listed["count"] == 2

        resp = json.loads(acp_tools._acp_respond_task(t1.task_id, {"echo": "a"}))
        assert resp["success"] is True

        rej = json.loads(acp_tools._acp_reject_task(t2.task_id, "not interested"))
        assert rej["success"] is True

        # Both resolved -- pending list is now empty
        assert json.loads(acp_tools._acp_pending_tasks())["count"] == 0
    finally:
        server.stop()
        state.set_server(None)


def test_respond_unknown_task_is_a_tool_error(free_port):
    cfg = AcpMeshConfig(agent_id="a", listen_port=free_port)
    server = AcpMeshServer(cfg, PendingTaskStore())
    server.start()
    state.set_server(server)
    try:
        out = acp_tools._acp_respond_task("nope", {"x": 1})
        assert "error" in json.loads(out)
    finally:
        server.stop()
        state.set_server(None)
