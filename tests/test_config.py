from acp_mesh.config import AcpMeshConfig, load_acp_mesh_config
from acp_mesh.protocol import Peer


def test_inbound_disabled_without_listen_port():
    cfg = AcpMeshConfig(agent_id="a")
    assert cfg.inbound_enabled is False
    assert cfg.endpoint is None


def test_inbound_enabled_with_listen_port():
    cfg = AcpMeshConfig(agent_id="a", listen_host="127.0.0.1", listen_port=8100)
    assert cfg.inbound_enabled is True
    assert cfg.endpoint == "http://127.0.0.1:8100"


def test_load_acp_mesh_config_falls_back_when_hermes_cli_unavailable():
    """This repo doesn't depend on hermes-agent, so hermes_cli.config isn't
    importable here -- exactly the scenario load_acp_mesh_config's except
    branch exists for. Prove it degrades to safe defaults instead of raising."""
    cfg = load_acp_mesh_config()
    assert isinstance(cfg, AcpMeshConfig)
    assert cfg.inbound_enabled is False
    assert cfg.registry_url is None
    assert cfg.peers == []


def test_peer_parsing_skips_malformed_entries(monkeypatch):
    import acp_mesh.config as config_mod

    monkeypatch.setattr(
        config_mod, "load_config",
        lambda: {"plugins": {"entries": {"acp-mesh": {
            "peers": [
                {"agent_id": "ok", "endpoint": "http://x"},
                {"agent_id": "missing-endpoint"},
            ],
        }}}},
        raising=False,
    )
    # load_acp_mesh_config does `from hermes_cli.config import load_config`
    # inside the function, so patch the import target it will resolve via
    # sys.modules instead of the (nonexistent) real package.
    import sys
    import types

    fake_hermes_cli = types.ModuleType("hermes_cli")
    fake_config_mod = types.ModuleType("hermes_cli.config")
    fake_config_mod.load_config = config_mod.load_config
    fake_hermes_cli.config = fake_config_mod
    sys.modules["hermes_cli"] = fake_hermes_cli
    sys.modules["hermes_cli.config"] = fake_config_mod
    try:
        cfg = load_acp_mesh_config()
    finally:
        del sys.modules["hermes_cli"]
        del sys.modules["hermes_cli.config"]

    assert cfg.peers == [Peer("ok", "http://x")]
