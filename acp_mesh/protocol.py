"""
Wire format for ACP (Agent Context Protocol) -- the same protocol defined in
the standalone reference implementation's ACP.md, reused here so a Hermes
agent and a plain-Python ACP node can talk to each other with no translation
layer. See that spec for the full rationale; this module just gives the two
JSON shapes (Agent Card, Task Envelope) a single typed home instead of
passing raw dicts around.

Not to be confused with acp_adapter/ elsewhere in this repo, which implements
the unrelated Agent Client Protocol (editor <-> coding-agent, e.g. Zed). Same
three letters, different protocol, different purpose -- see plugins/acp_mesh/
README.md for the disambiguation.
"""

from __future__ import annotations

import dataclasses
import time
import uuid
from typing import Any, Dict, List, Optional

ACP_VERSION = "0.1"


@dataclasses.dataclass
class Peer:
    agent_id: str
    endpoint: str

    def to_dict(self) -> Dict[str, str]:
        return {"agent_id": self.agent_id, "endpoint": self.endpoint}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Peer":
        return cls(agent_id=str(data["agent_id"]), endpoint=str(data["endpoint"]))


@dataclasses.dataclass
class AgentCard:
    agent_id: str
    endpoint: str
    capabilities: List[str]
    name: str = ""
    description: str = ""
    peers: List[Peer] = dataclasses.field(default_factory=list)
    acp_version: str = ACP_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return {
            "acp_version": self.acp_version,
            "agent_id": self.agent_id,
            "name": self.name,
            "description": self.description,
            "endpoint": self.endpoint,
            "capabilities": list(self.capabilities),
            "peers": [p.to_dict() for p in self.peers],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentCard":
        return cls(
            agent_id=str(data["agent_id"]),
            endpoint=str(data["endpoint"]),
            capabilities=list(data.get("capabilities", [])),
            name=str(data.get("name", "")),
            description=str(data.get("description", "")),
            peers=[Peer.from_dict(p) for p in data.get("peers", [])],
            acp_version=str(data.get("acp_version", ACP_VERSION)),
        )


@dataclasses.dataclass
class TaskEnvelope:
    task_id: str
    capability: str
    input: Dict[str, Any]
    ttl: int
    origin: str
    trace: List[str] = dataclasses.field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "capability": self.capability,
            "input": self.input,
            "ttl": self.ttl,
            "origin": self.origin,
            "trace": list(self.trace),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskEnvelope":
        return cls(
            task_id=str(data["task_id"]),
            capability=str(data["capability"]),
            input=dict(data.get("input") or {}),
            ttl=int(data.get("ttl", 0)),
            origin=str(data.get("origin", "")),
            trace=list(data.get("trace", [])),
        )

    def forwarded(self, via_agent_id: str) -> "TaskEnvelope":
        """Return a copy ready to hand to the next hop: ttl-1, trace+[us]."""
        return dataclasses.replace(
            self, ttl=self.ttl - 1, trace=[*self.trace, via_agent_id]
        )


def new_task_id() -> str:
    return f"hermes-{uuid.uuid4().hex[:16]}"


def now() -> float:
    return time.time()
