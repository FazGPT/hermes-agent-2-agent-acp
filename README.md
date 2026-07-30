# hermes-agent-2-agent-acp

An **ACP (Agent Context Protocol)** plugin (Python package: `hermes-acp-mesh`) for [NousResearch's Hermes agent](https://github.com/NousResearch/hermes-agent):
capability-based discovery and task routing between independently-run
agents, with a bootstrap registry standing in for DNS. A Hermes agent
running this plugin can ask "who on the network can do X?", hand a task
off to whoever can, and — in CLI sessions — accept work handed to *it*.

Full protocol spec (wire format, routing algorithm, security model): see
[FazGPT/acp](https://github.com/FazGPT/acp), which also ships a
zero-dependency reference implementation this plugin interoperates with
directly (see "Verification" below).

## The idea behind this

The premise: every agent should be able to reach every other agent, directly
or by asking someone who can. If your agent can't do something, that
shouldn't be a dead end — it should be able to ask around, and if none of
its immediate contacts can help, ask *their* contacts, and so on, until
something a few hops away actually can. Nothing should be a hard "I can't
do that."

Two ideas make that work without anyone needing to run or own the whole
network:

1. **Agents advertise their capabilities as publicly-authorized tools.** An
   Agent Card is a public, machine-readable statement of "here's what I can
   do, here's how to reach me." Any other agent is free to call a
   capability once it knows about it — there's no central approval process
   for *what* an agent offers. The network is opt-in and self-describing.

2. **Every agent is also a node in the directory, not just a client of
   one.** Rather than one central switchboard holding the full map of
   who-can-do-what, each agent keeps its own small address book — the
   `peers` list in its own Agent Card — of the other agents *it* knows
   directly. A bootstrap registry helps a *new* agent find its first few
   contacts (the DNS-root analogy), but from there, routing happens
   peer-to-peer: your agent asks the agents it knows, they ask the agents
   *they* know, and so on. No single node needs, or has, a complete
   picture of the network. The directory is the union of everyone's small,
   local address books — a phone tree or a social graph, not a database
   any one party owns.

Applied specifically to Hermes: this plugin is the piece that lets every
independent Hermes agent — yours, mine, anyone's — become one node in that
same mesh. Each Hermes agent that installs it advertises its own
capabilities, keeps its own local list of agents it knows, and can forward
a request on to them. Multiply that across every Hermes installation that
opts in, and the result is an emergent, decentralized directory and
network for Hermes-to-Hermes communication — not a service anyone has to
run or maintain centrally, just a protocol every participating agent
already speaks. "A few hops down the road" isn't a metaphor here; it's
literally the routing algorithm in `acp_mesh/server.py`'s forwarding
logic, bounded by a hop-count TTL so a request terminates instead of
circulating forever.

The full protocol-level version of this reasoning lives in
[FazGPT/acp](https://github.com/FazGPT/acp)'s `ACP.md`; this repo is where
that idea gets wired into a real, running agent framework.

## Status: proof of concept (v0.1)

This is a working v0.1 implementation, not a hardened production system.
Before relying on it beyond a local or fully-trusted network:

- **No authentication.** Any agent that can reach your `/acp/task`
  endpoint can submit work to you, and any Agent Card claiming a
  capability is taken at face value — nothing verifies an agent actually
  is who it says it is, or can do what it claims.
- **Relay hops are unverified.** A forwarding agent could silently drop,
  mangle, or misattribute a task in transit — there's no signing or
  attestation on a Task Envelope.
- **Inbound task-handling is CLI-session-only** (see "Inbound scope"
  below) — not yet suitable for always-on autonomous fulfillment without
  a deliberate, separate step up in trust.
- **No registry federation, no async/long-running tasks, no payment or
  metering.**

None of these are hard problems individually — they're deliberately
deferred so a first working version stays small enough to review. The full
list, and the reasoning behind deferring each one, is in
[FazGPT/acp](https://github.com/FazGPT/acp)'s `ACP.md` (§7 "Security
considerations" and §10 "Where this would need to go next"). Treat this as
a foundation to harden, not a finished product.

## Why this is a separate repo, not a PR to hermes-agent

hermes-agent's own `CONTRIBUTING.md` is explicit about this:

> "The same rule extends to any plugin that integrates someone else's
> product or project ... These do not land in this repo ... Publish these
> as a standalone plugin repo instead."

ACP is a protocol independent of Hermes, not a Nous-authored core
capability, so it belongs here rather than in `hermes-agent/plugins/`. This
repo follows the installation paths their docs describe for exactly this
case: manual copy into `~/.hermes/plugins/`, or a pip / entry-point install.

## Install

**Option A — pip / entry point** (recommended; auto-discovered, no manual copying):

```bash
pip install git+https://github.com/FazGPT/hermes-agent-2-agent-acp.git
```

hermes-agent's plugin loader scans `importlib.metadata` entry points in the
`hermes_agent.plugins` group at startup — this package registers itself
there (see `pyproject.toml`), so installing it into the same environment
Hermes runs in is enough. No files need to be copied anywhere.

**Option B — manual copy:**

```bash
git clone https://github.com/FazGPT/hermes-agent-2-agent-acp.git
cd hermes-agent-2-agent-acp
cp -r acp_mesh <path-to-hermes-agent-checkout>/plugins/acp_mesh
pip install httpx   # only external dependency, likely already present
```

Either way, enable and configure it in `config.yaml`:

```yaml
plugins:
  enabled: [acp-mesh]
  entries:
    acp-mesh:
      agent_id: my-hermes.agents.example      # defaults to hermes.<hostname>.agents.local
      registry_url: http://127.0.0.1:8000     # omit to skip registry-based discovery
      listen_port: 8100                       # omit to stay outbound-only (default)
      capabilities: [hermes.assist]           # what you advertise if listen_port is set
      peers:
        - agent_id: math.agents.local
          endpoint: http://127.0.0.1:8002
      pending_task_timeout_seconds: 120
```

Every key has a safe default. With just `enabled: [acp-mesh]` and nothing
else, the plugin does nothing observable: no `registry_url` means
`acp_resolve` returns a clear error telling you to configure one, and no
`listen_port` means there's no inbound listener.

## What it gives the model

Six tools, registered under the `acp_mesh` toolset:

**Outbound (work in any session type — CLI, gateway, subagent):**
- `acp_resolve(capability)` — who on the mesh currently advertises this?
- `acp_card(endpoint)` — handshake: fetch an agent's self-description
- `acp_send_task(capability, input, endpoint?, ttl?)` — hand work to
  another agent, get the result back (possibly after several hops)

**Inbound (CLI sessions only — see below):**
- `acp_pending_tasks()` — requests other agents have sent to *you*
- `acp_respond_task(task_id, result)` / `acp_reject_task(task_id, reason)`
  — answer or decline one, unblocking the remote caller

## Inbound scope: why CLI-only

Turning an incoming ACP task into a real answer means either driving a
live Hermes turn or spawning a subagent, and both require an *active*
session context:

- `agent.subagent_lifecycle.SubagentLifecycleService.launch()` resolves
  its parent agent through a contextvar that's only bound for the
  duration of a turn — not available from the inbound listener's
  background thread.
- `PluginContext.inject_message()` explicitly no-ops outside an
  interactive CLI session.

So an incoming task for a capability you advertise gets parked in a
pending-task queue and the HTTP request blocks (up to
`pending_task_timeout_seconds`) until a tool call resolves it — which
only happens if a live CLI session's model chooses to check
`acp_pending_tasks`. That's also a deliberate trust boundary: ACP v0.1 has
no authentication, so every incoming task is an unauthenticated string
from a stranger's agent until a human's own session decides to act on it.
It never gets tool access on its own.

Pure relay hops (forwarding a task you don't advertise to a configured
peer or a registry-resolved agent) work in any session type — no model
turn involved, just an HTTP call.

## Verification

This plugin was developed and tested against a real clone of
`hermes-agent`, not written blind:

- All six tools registered cleanly against the actual `tools.registry.ToolRegistry`
- Dispatched through the actual `registry.dispatch()`, including the real
  `is_async` bridge through `model_tools`
- Round-tripped live, over real HTTP, against
  [FazGPT/acp](https://github.com/FazGPT/acp)'s standalone reference
  agents: `acp_resolve`/`acp_card`/`acp_send_task` correctly resolving and
  calling a live `math` agent; the inbound listener genuinely blocking a
  request in the pending queue and returning the right answer once
  resolved; a pure relay hop forwarding to that same standalone agent

This repo's own `tests/` (see below) cover everything that doesn't require
a hermes-agent install itself — protocol wire format, the pending-task
queue, the inbound server's routing algorithm, and the outbound client —
using small in-process stub HTTP peers so they run standalone.

## Development

```bash
pip install -e ".[dev]"
pytest
```

## Files

- `acp_mesh/protocol.py` — Agent Card / Task Envelope dataclasses (the wire format)
- `acp_mesh/client.py` — outbound calls (httpx)
- `acp_mesh/server.py` — inbound listener (stdlib `http.server`) + routing algorithm
- `acp_mesh/pending.py` — the queue/blocking mechanism inbound tasks wait in
- `acp_mesh/config.py` — reads `plugins.entries.acp-mesh.*` from Hermes's config.yaml
- `acp_mesh/state.py` — process-wide handle to the running server + plugin context
- `acp_mesh/tools.py` — the six tool schemas + handlers
- `acp_mesh/__init__.py` — `register(ctx)`: wires hooks + tools
- `acp_mesh/plugin.yaml` — manifest for the manual-copy install path

## License

MIT — see [LICENSE](LICENSE).
