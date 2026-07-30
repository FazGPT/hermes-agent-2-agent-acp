"""acp_mesh -- connects a Hermes agent to an ACP (Agent Context Protocol) mesh.

Not to be confused with acp_adapter/ elsewhere in this repo (the unrelated
Agent Client Protocol used for editor integration, e.g. Zed). See README.md
for the full disambiguation.

Wires:
  - on_session_start / on_session_end -- start/stop the inbound listener
    (server.py) and register this agent's Agent Card with the configured
    registry. No-ops entirely if listen_port isn't configured (outbound-only
    is the default -- see config.py).
  - Six tools (tools.py) -- three outbound (work anywhere), three inbound
    (CLI sessions only; see pending.py for why).
"""

from __future__ import annotations

import logging
from typing import Any

from . import client, state
from .config import load_acp_mesh_config
from .pending import PendingTaskStore
from .server import AcpMeshServer
from .tools import TOOL_DEFS

logger = logging.getLogger(__name__)


def _on_session_start(**kwargs: Any) -> None:
    cfg = load_acp_mesh_config()
    server = AcpMeshServer(cfg, PendingTaskStore())
    server.start()
    state.set_server(server)

    if cfg.inbound_enabled and cfg.registry_url:
        # Best-effort, bounded sync call -- see client.register_with_sync's
        # docstring for why this isn't async despite everything else here
        # preferring httpx.AsyncClient.
        client.register_with_sync(cfg.registry_url, server.card())


def _on_session_end(**kwargs: Any) -> None:
    server = state.get_server()
    if server is not None:
        server.stop()
    state.set_server(None)


def register(ctx) -> None:
    state.set_ctx(ctx)
    ctx.register_hook("on_session_start", _on_session_start)
    ctx.register_hook("on_session_end", _on_session_end)
    for tool_def in TOOL_DEFS:
        ctx.register_tool(**tool_def)
    logger.debug("acp_mesh: registered %d tools", len(TOOL_DEFS))
