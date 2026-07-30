from acp_mesh.protocol import AgentCard, Peer, TaskEnvelope, new_task_id


def test_agent_card_round_trip():
    card = AgentCard(
        agent_id="a.agents.test",
        endpoint="http://127.0.0.1:8100",
        capabilities=["x.y"],
        name="Test",
        description="desc",
        peers=[Peer("b.agents.test", "http://127.0.0.1:8101")],
    )
    restored = AgentCard.from_dict(card.to_dict())
    assert restored == card


def test_agent_card_from_dict_defaults():
    card = AgentCard.from_dict({"agent_id": "a", "endpoint": "http://x"})
    assert card.capabilities == []
    assert card.peers == []
    assert card.acp_version == "0.1"


def test_task_envelope_round_trip():
    task = TaskEnvelope(
        task_id="t1", capability="x.y", input={"a": 1}, ttl=4,
        origin="a.agents.test", trace=["a.agents.test"],
    )
    restored = TaskEnvelope.from_dict(task.to_dict())
    assert restored == task


def test_task_envelope_forwarded_decrements_ttl_and_appends_trace():
    task = TaskEnvelope("t1", "x.y", {}, ttl=4, origin="a", trace=["a"])
    fwd = task.forwarded("b")
    assert fwd.ttl == 3
    assert fwd.trace == ["a", "b"]
    # original untouched
    assert task.ttl == 4
    assert task.trace == ["a"]


def test_new_task_id_is_unique():
    ids = {new_task_id() for _ in range(100)}
    assert len(ids) == 100
