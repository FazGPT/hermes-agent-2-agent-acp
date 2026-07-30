"""Process-wide handle to the currently-running AcpMeshServer, if any.

Kept separate from __init__.py (rather than a module attribute there) so
tools.py can read it without importing the plugin's register() module --
keeps the import graph a simple line: state.py <- {tools.py, __init__.py},
no cycle.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .server import AcpMeshServer

_server: "Optional[AcpMeshServer]" = None
_ctx: Optional[object] = None


def set_server(server: "Optional[AcpMeshServer]") -> None:
    global _server
    _server = server


def get_server() -> "Optional[AcpMeshServer]":
    return _server


def set_ctx(ctx: Optional[object]) -> None:
    """Stash the PluginContext so server.py can best-effort call
    ctx.inject_message() from the HTTP handler thread when a new task is
    queued. Only used for that one notification -- everything else the
    plugin does goes through ctx once, at register() time."""
    global _ctx
    _ctx = ctx


def get_ctx() -> Optional[object]:
    return _ctx
