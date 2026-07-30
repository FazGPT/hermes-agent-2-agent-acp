"""
Settings for the acp_mesh plugin, read from config.yaml under
``plugins.entries.acp-mesh.*`` -- the same place ``allow_tool_override`` and
other per-plugin options live (see PluginContext._tool_override_allowed for
the established pattern this follows).

Example config.yaml block::

    plugins:
      enabled: [acp-mesh]
      entries:
        acp-mesh:
          agent_id: my-hermes.agents.example
          listen_host: 127.0.0.1
          listen_port: 8100
          registry_url: http://127.0.0.1:8000
          capabilities: [hermes.assist]
          peers:
            - agent_id: math.agents.local
              endpoint: http://127.0.0.1:8002
          pending_task_timeout_seconds: 120

Every key has a safe default so the plugin does something reasonable
(outbound-only, no inbound listener) even with zero configuration.
"""

from __future__ import annotations

import logging
import socket
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .protocol import Peer

logger = logging.getLogger(__name__)

PLUGIN_ID = "acp-mesh"


@dataclass
class AcpMeshConfig:
    agent_id: str
    listen_host: str = "127.0.0.1"
    listen_port: Optional[int] = None
    registry_url: Optional[str] = None
    capabilities: List[str] = field(default_factory=list)
    peers: List[Peer] = field(default_factory=list)
    pending_task_timeout_seconds: float = 120.0

    @property
    def inbound_enabled(self) -> bool:
        """Only listen for incoming tasks when a port is explicitly configured.

        Outbound-only (no listen_port) is the safe default: this Hermes agent
        can still call out to the mesh via acp_resolve/acp_send_task, it just
        isn't reachable by other agents. See README.md 'Inbound scope' for
        why inbound is opt-in rather than on-by-default.
        """
        return self.listen_port is not None

    @property
    def endpoint(self) -> Optional[str]:
        if not self.inbound_enabled:
            return None
        return f"http://{self.listen_host}:{self.listen_port}"


def _default_agent_id() -> str:
    host = socket.gethostname().split(".")[0].lower() or "host"
    return f"hermes.{host}.agents.local"


def load_acp_mesh_config() -> AcpMeshConfig:
    """Read this plugin's settings. Never raises -- falls back to safe
    (outbound-only) defaults on any config error so a malformed block can't
    take the whole plugin down.
    """
    try:
        from hermes_cli.config import load_config
        cfg = load_config() or {}
    except Exception as e:
        logger.debug("acp_mesh: could not load hermes config (%s); using defaults", e)
        cfg = {}

    entries = ((cfg.get("plugins") or {}).get("entries") or {})
    raw: Dict[str, Any] = entries.get(PLUGIN_ID) or {}

    peers_raw = raw.get("peers") or []
    peers: List[Peer] = []
    for p in peers_raw:
        try:
            peers.append(Peer.from_dict(p))
        except (KeyError, TypeError) as e:
            logger.warning("acp_mesh: skipping malformed peer entry %r (%s)", p, e)

    return AcpMeshConfig(
        agent_id=str(raw.get("agent_id") or _default_agent_id()),
        listen_host=str(raw.get("listen_host") or "127.0.0.1"),
        listen_port=raw.get("listen_port"),
        registry_url=raw.get("registry_url"),
        capabilities=list(raw.get("capabilities") or []),
        peers=peers,
        pending_task_timeout_seconds=float(raw.get("pending_task_timeout_seconds", 120.0)),
    )
