import pytest

from acp_mesh import client
from acp_mesh.protocol import AgentCard, TaskEnvelope, new_task_id


@pytest.mark.asyncio
async def test_get_card(fake_peer):
    card = await client.get_card(fake_peer)
    assert card.agent_id == "fake-peer.agents.test"
    assert "test.add" in card.capabilities


@pytest.mark.asyncio
async def test_send_task(fake_peer):
    task = TaskEnvelope(new_task_id(), "test.add", {"a": 19, "b": 23}, 4, "tester", [])
    result = await client.send_task(fake_peer, task)
    assert result["status"] == "ok"
    assert result["result"]["sum"] == 42


@pytest.mark.asyncio
async def test_send_task_unsupported_capability_returns_structured_error(fake_peer):
    task = TaskEnvelope(new_task_id(), "nope.nope", {}, 4, "tester", [])
    result = await client.send_task(fake_peer, task)
    assert result["status"] == "error"


@pytest.mark.asyncio
async def test_register_and_resolve_round_trip(fake_registry):
    card = AgentCard(
        agent_id="a.agents.test", endpoint="http://127.0.0.1:9999",
        capabilities=["x.y"],
    )
    await client.register_with(fake_registry, card)
    found = await client.resolve(fake_registry, "x.y")
    assert len(found) == 1
    assert found[0].agent_id == "a.agents.test"


@pytest.mark.asyncio
async def test_resolve_no_match_returns_empty(fake_registry):
    found = await client.resolve(fake_registry, "nobody.has.this")
    assert found == []


def test_register_with_sync_never_raises_on_unreachable_registry():
    card = AgentCard(agent_id="a", endpoint="http://127.0.0.1:1", capabilities=[])
    # Port 1 is not listening -- this should fail fast and return None,
    # not raise, per register_with_sync's docstring guarantee.
    result = client.register_with_sync("http://127.0.0.1:1", card, timeout=1.0)
    assert result is None
