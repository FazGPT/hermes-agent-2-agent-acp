"""Shared fixtures. No hermes-agent install required -- everything here
exercises acp_mesh against itself or a tiny in-process stub peer, the same
technique used to manually verify this plugin against a real hermes-agent
clone (see the project README for that verification writeup)."""

from __future__ import annotations

import json
import socket
import threading
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest


def _free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _FakePeerHandler(BaseHTTPRequestHandler):
    """A trivial ACP agent: handles capability 'test.add' locally, otherwise
    404s. Enough to exercise relay-forwarding and acp_resolve against a real
    HTTP round trip without needing a full agent implementation."""

    agent_id = "fake-peer.agents.test"
    capabilities = ["test.add"]

    def log_message(self, fmt, *args):
        pass

    def _send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/.well-known/acp.json":
            self._send_json(200, {
                "acp_version": "0.1",
                "agent_id": self.agent_id,
                "name": "Fake Peer",
                "description": "",
                "endpoint": f"http://127.0.0.1:{self.server.server_address[1]}",
                "capabilities": self.capabilities,
                "peers": [],
            })
            return
        self._send_json(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/acp/task":
            self._send_json(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length", 0))
        task = json.loads(self.rfile.read(length))
        if task["capability"] == "test.add":
            a, b = task["input"]["a"], task["input"]["b"]
            self._send_json(200, {
                "status": "ok",
                "result": {"sum": a + b},
                "handled_by": self.agent_id,
                "trace": [*task.get("trace", []), self.agent_id],
            })
            return
        self._send_json(404, {
            "status": "error", "error": "no known route for capability",
            "trace": task.get("trace", []),
        })


@pytest.fixture()
def fake_peer():
    """Start a fake ACP peer on a free port; yield its base endpoint URL."""
    port = _free_port()
    httpd = ThreadingHTTPServer(("127.0.0.1", port), _FakePeerHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        httpd.shutdown()
        httpd.server_close()


@pytest.fixture()
def free_port():
    return _free_port()


class _FakeRegistryHandler(BaseHTTPRequestHandler):
    """Minimal stand-in for src/registry_server.py from the protocol repo:
    POST /register stores a card, GET /resolve?capability=X returns matches."""

    registered: dict = {}

    def log_message(self, fmt, *args):
        pass

    def _send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/register":
            self._send_json(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length", 0))
        card = json.loads(self.rfile.read(length))
        type(self).registered[card["agent_id"]] = card
        self._send_json(200, {"status": "registered"})

    def do_GET(self):
        if not self.path.startswith("/resolve"):
            self._send_json(404, {"error": "not found"})
            return
        from urllib.parse import urlparse, parse_qs
        qs = parse_qs(urlparse(self.path).query)
        capability = (qs.get("capability") or [None])[0]
        matches = [
            c for c in type(self).registered.values()
            if capability in c.get("capabilities", [])
        ]
        self._send_json(200, {"capability": capability, "agents": matches})


@pytest.fixture()
def fake_registry():
    _FakeRegistryHandler.registered = {}
    port = _free_port()
    httpd = ThreadingHTTPServer(("127.0.0.1", port), _FakeRegistryHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        httpd.shutdown()
        httpd.server_close()
