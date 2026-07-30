"""
Outbound ACP calls. Async (httpx.AsyncClient) because these run as
is_async=True tool handlers, bridged through tools/registry.py's
_run_async() -- see tools/web_tools.py's web_extract_tool for the
established pattern this follows.

register_with_sync() is the one exception: session-start registration runs
from a plugin hook (on_session_start), and hooks are invoked synchronously
by PluginManager.invoke_hook() (plain `cb(**kwargs)`, never awaited -- an
async def hook callback would silently return an un-awaited coroutine and
do nothing). A single short, timeout-bounded sync POST at startup is the
simplest correct fix; see pending.py's module docstring for why the rest of
the inbound path avoids blocking hook/handler threads on agent internals.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import httpx

from .protocol import AgentCard, TaskEnvelope

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 10.0


async def get_card(endpoint: str, *, timeout: float = _DEFAULT_TIMEOUT) -> AgentCard:
    """Handshake: GET <endpoint>/.well-known/acp.json"""
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(f"{endpoint.rstrip('/')}/.well-known/acp.json")
        resp.raise_for_status()
        return AgentCard.from_dict(resp.json())


async def resolve(registry_url: str, capability: str, *, timeout: float = _DEFAULT_TIMEOUT) -> List[AgentCard]:
    """GET <registry>/resolve?capability=X -> agents currently advertising it."""
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(
            f"{registry_url.rstrip('/')}/resolve", params={"capability": capability}
        )
        resp.raise_for_status()
        data = resp.json()
        return [AgentCard.from_dict(c) for c in data.get("agents", [])]


async def send_task(
    endpoint: str, task: TaskEnvelope, *, timeout: float = _DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    """POST a Task Envelope to <endpoint>/acp/task and return the parsed result.

    Mirrors demo/client.py's send_task() in the standalone reference impl --
    same wire format, same endpoint shape, so this can talk to those toy
    math/weather/translator agents directly (see plugins/acp_mesh/README.md
    for a worked cross-implementation example).
    """
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            f"{endpoint.rstrip('/')}/acp/task", json=task.to_dict()
        )
        # Agents return a structured JSON error body even on 4xx/5xx
        # (see server.py's _send_json paths) -- surface that instead of
        # raising, so the caller gets {"status": "error", ...} either way.
        try:
            return resp.json()
        except ValueError:
            resp.raise_for_status()
            raise


async def register_with(
    registry_url: str, card: AgentCard, *, timeout: float = _DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(f"{registry_url.rstrip('/')}/register", json=card.to_dict())
        resp.raise_for_status()
        return resp.json()


def register_with_sync(
    registry_url: str, card: AgentCard, *, timeout: float = 5.0
) -> Optional[Dict[str, Any]]:
    """Best-effort sync registration for on_session_start. Never raises --
    a registry that's down at startup shouldn't block the agent from
    starting; outbound tools (acp_resolve/acp_send_task) still work against
    directly-configured peers even if the registry never answered.
    """
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(f"{registry_url.rstrip('/')}/register", json=card.to_dict())
            resp.raise_for_status()
            return resp.json()
    except (httpx.HTTPError, OSError) as e:
        logger.warning("acp_mesh: could not register with registry %s: %s", registry_url, e)
        return None
