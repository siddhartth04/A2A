# A2A Greeting Demo

A working demo of the **Agent2Agent (A2A) Protocol** — two Python agents communicating over the official Linux Foundation [`a2a-sdk`](https://pypi.org/project/a2a-sdk/).

A **Greeting Agent** (server) exposes a `greet` skill over HTTP/JSON-RPC. A **Client Agent** discovers it via its public Agent Card, sends a name, and streams back the greeting through the full A2A task lifecycle.

> **Author:** Siddharth Yadav
> **Protocol:** A2A v1.0
> **Stack:** `a2a-sdk` · Starlette · uvicorn · httpx · rich

---

## Architecture

```
┌─────────────────┐                                ┌─────────────────┐
│  CLIENT AGENT   │                                │ GREETING AGENT  │
│  (client.py)    │                                │  (server)       │
│                 │  1. GET /agent-card.json       │                 │
│                 │ ─────────────────────────────▶ │                 │
│                 │ ◀──── AgentCard JSON ───────── │                 │
│                 │                                │                 │
│                 │  2. POST /  (JSON-RPC)         │                 │
│                 │ ───── SendMessageRequest ────▶ │                 │
│                 │                                │   ▼ executor    │
│                 │ ◀──── SSE stream ───────────── │   ▼ enqueues    │
│                 │   • task (SUBMITTED)           │   ▼ events      │
│                 │   • status (WORKING)           │                 │
│                 │   • artifact (greeting)        │                 │
│                 │   • status (COMPLETED)         │                 │
└─────────────────┘                                └─────────────────┘
```

The protocol underneath is just **HTTP + JSON-RPC + Server-Sent Events**, with strict schemas defined by protobuf-backed types in `a2a.types`.

---

## Project Structure

```
a2a_greeting_demo/
├── run_demo.py                    # Orchestrator — boots server + runs client
├── greeting_agent/                # Server side
│   ├── __init__.py
│   ├── __main__.py                # Agent Card + Starlette app wiring
│   └── agent_executor.py          # Business logic + A2A executor
├── client_agent/                  # Client side
│   ├── __init__.py
│   └── client.py                  # Discovery, request, stream consumption
├── HOW_IT_WORKS.md                # Detailed component-by-component walkthrough
└── README.md
```

---

## Features

- **Discovery** via public Agent Card at `/.well-known/agent-card.json`
- **Tiered access** — public + extended Agent Cards (extended visible only to authenticated clients)
- **Streaming task lifecycle** over SSE: `SUBMITTED → WORKING → ARTIFACT → COMPLETED`
- **Clean separation** — protocol layer (executor) vs business logic (`GreetingAgent`)
- **Rich CLI output** — colored events, panels, and progress rendering

---

## Quick Start

### Prerequisites

- Python 3.11+
- pip

### Installation

```bash
# Clone the repo
git clone https://github.com/siddhartth04/A2A.git
cd A2A

# Create a virtual environment
python -m venv .venv

# Activate it
# Windows (PowerShell):
.\.venv\Scripts\Activate.ps1
# macOS / Linux:
source .venv/bin/activate

# Install dependencies (uses requirements.txt with pinned versions)
pip install -r requirements.txt
```

> **Why a `requirements.txt`?** `a2a-sdk 1.0.x` is incompatible with `protobuf>=6`. Plain `pip install a2a-sdk` will pull the latest protobuf and crash with `FieldDescriptor object has no attribute 'label'`. The requirements file pins `protobuf>=5,<6` to avoid this.

### Run

**One command (recommended):**

```bash
python run_demo.py                  # greets "Siddharth"
python run_demo.py "Alice"          # custom name
```

**Or run server and client separately** — server in one terminal:

```bash
python -m greeting_agent
```

Client in another:

```bash
python -m client_agent.client "Alice"
```

---

## Expected Output

1. Server boots on `http://127.0.0.1:9999`
2. Client fetches the Agent Card and prints capabilities + skills
3. Client sends the name as a `ROLE_USER` message
4. Stream events print in order:
   - `← task` (SUBMITTED, with task id)
   - `← status_update` (WORKING)
   - `← artifact_update` (the greeting text)
   - `← status_update` (COMPLETED)
5. Final greeting renders in a green panel:

```
╭───── ✅  GREETING RESULT ─────╮
│                                │
│  Hello, Alice! 👋  Welcome     │
│  to the A2A Protocol Demo.     │
│                                │
╰────────────────────────────────╯
```

---

## How It Works

For a deep walkthrough of every component (Agent Card, executor, request handler, client streaming, wire-level traffic), see **[HOW_IT_WORKS.md](HOW_IT_WORKS.md)**.

### Mental model in one paragraph

The A2A SDK gives you typed protobuf models (`AgentCard`, `Task`, `Message`, `Artifact`) and protocol plumbing (`DefaultRequestHandler`, `A2ACardResolver`, `ClientFactory`). You write **two things**: an **Agent Card** that declares what your agent does, and an **`AgentExecutor`** that runs your logic and emits lifecycle events onto an `EventQueue`. Starlette + uvicorn host it. The client fetches the card, picks a transport based on declared capabilities, sends a `Message`, and consumes a stream of typed events. That's it.

---

## Key SDK Components Used

### Server side

| Component | Role |
|---|---|
| `AgentCard`, `AgentSkill`, `AgentCapabilities`, `AgentInterface` | Public identity & advertised features |
| `AgentExecutor` (interface) | Implemented by `GreetingAgentExecutor` to run business logic |
| `DefaultRequestHandler` | SDK protocol brain — validates, routes, serializes |
| `InMemoryTaskStore` | Task state storage (use Redis/Postgres in production) |
| `create_agent_card_routes`, `create_jsonrpc_routes` | Wire routes into Starlette |
| `Task`, `TaskStatusUpdateEvent`, `TaskArtifactUpdateEvent` | Lifecycle events emitted by executor |

### Client side

| Component | Role |
|---|---|
| `A2ACardResolver` | Fetches `/.well-known/agent-card.json` |
| `ClientFactory` + `ClientConfig` | Creates a transport-aware client from the card |
| `SendMessageRequest`, `Message`, `Part`, `Role` | Build outgoing messages |
| `StreamResponse` (protobuf `oneof`) | Per-chunk event in the SSE stream |

---

## Technical Highlights

- **Idempotency** — every `Message` carries a `message_id`; resending the same id is a no-op
- **Multi-modal ready** — messages and artifacts use a `parts` list (`text`, `file`, `data`)
- **Transport-agnostic clients** — the card declares the transport (here: JSON-RPC); `ClientFactory` returns the right concrete client
- **`oneof` event multiplexing** — a single `StreamResponse` carries either `task`, `status_update`, `artifact_update`, or `message`; the client uses `HasField()` to dispatch
- **Async streaming** — Starlette's `StreamingResponse` keeps the HTTP connection open while the executor enqueues events one at a time

---

## Troubleshooting

**`ModuleNotFoundError: No module named 'a2a'`**
You're running outside the virtual environment, or the SDK isn't installed. Activate the venv and run `pip install -r requirements.txt`.

**`ModuleNotFoundError: No module named 'sse_starlette'`**
The `a2a-sdk` was installed without the `[http-server]` extra. Run `pip install -r requirements.txt` (or `pip install "a2a-sdk[http-server]"`).

**`AttributeError: 'google._upb._message.FieldDescriptor' object has no attribute 'label'`**
You have `protobuf>=6` installed, which is incompatible with `a2a-sdk 1.0.x`. Run `pip install "protobuf>=5,<6"`.

**Garbled glyphs / `UnicodeEncodeError: 'charmap' codec` on Windows**
Already handled by `run_demo.py` and `client.py` — they reconfigure stdout to UTF-8. If you still see issues, set `set PYTHONIOENCODING=utf-8` (cmd) or `$env:PYTHONIOENCODING="utf-8"` (PowerShell) before running.

**`Port 9999 already in use`**
Another process is using the port. Change `PORT` in [`greeting_agent/__main__.py`](greeting_agent/__main__.py) and update `SERVER_BASE_URL` in [`client_agent/client.py`](client_agent/client.py) to match.

**Server starts but client times out**
Check firewall settings — `127.0.0.1:9999` must be reachable locally. The orchestrator polls for 10 seconds before giving up.

---

## License

MIT — feel free to fork, adapt, and extend.

---

## Author

**Siddharth Yadav**
GitHub: [@siddhartth04](https://github.com/siddhartth04)
