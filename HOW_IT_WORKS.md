# How the A2A Greeting Demo Works

A complete walkthrough of every component in this project — what it does, how it does it, and how the pieces connect.

---

## Table of Contents

1. [The Big Picture](#1-the-big-picture)
2. [Project Structure](#2-project-structure)
3. [Component 1 — The Agent Card](#3-component-1--the-agent-card)
4. [Component 2 — The Server Wiring](#4-component-2--the-server-wiring)
5. [Component 3 — The Executor](#5-component-3--the-executor)
6. [Component 4 — The Client Flow](#6-component-4--the-client-flow)
7. [Component 5 — The Orchestrator](#7-component-5--the-orchestrator)
8. [Wire-Level Trace](#8-wire-level-trace)
9. [Separation of Concerns](#9-separation-of-concerns)
10. [How to Run](#10-how-to-run)

---

## 1. The Big Picture

This project is a working demo of the **A2A (Agent2Agent) Protocol** by the Linux Foundation. Two Python agents communicate via the official `a2a-sdk`:

- A **Greeting Agent** (server) — exposes a "greet" skill over HTTP/JSON-RPC.
- A **Client Agent** — discovers the server, sends a name, streams back the greeting.

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

**The protocol underneath is just:** HTTP + JSON-RPC + Server-Sent Events, with strict schemas defined by protobuf-backed types in `a2a.types`.

---

## 2. Project Structure

```
a2a_greeting_demo/
├── run_demo.py                    # Orchestrator — boots server + runs client
├── greeting_agent/                # Server side
│   ├── __init__.py
│   ├── __main__.py                # Agent Card + Starlette app
│   └── agent_executor.py          # Business logic + A2A executor
└── client_agent/                  # Client side
    ├── __init__.py
    └── client.py                  # Discovery, request, stream consumption
```

---

## 3. Component 1 — The Agent Card

**File:** `greeting_agent/__main__.py` → `build_agent_card()` (lines 35–86)

### What it does

Defines the agent's "business card" — its public identity that any A2A client can discover.

### How it does it

Builds protobuf objects from `a2a.types`:

| Object | Purpose |
|---|---|
| `AgentSkill` | One capability (id `greet`, tags, examples). Like a function signature for AI agents. |
| `AgentCapabilities` | Boolean flags: `streaming=True`, `extended_agent_card=True`. Tells clients which transport patterns to use. |
| `AgentInterface` | The transport binding: `JSONRPC` over `http://127.0.0.1:9999`. |
| `AgentCard` | The whole card — name, version, description, capabilities, interfaces, skills. |

### Two cards, two access tiers

The function returns:

- **Public card** with one skill (`greet`) — anyone can fetch it.
- **Extended card** with both skills (`greet` + `greet_formal`) — only authenticated clients see it.

This separation is an A2A-standard pattern for tiered access.

### Why `/.well-known/agent-card.json`?

A2A convention (like `/.well-known/openid-configuration` for OAuth). Clients always know where to look for discovery.

---

## 4. Component 2 — The Server Wiring

**File:** `greeting_agent/__main__.py` → `create_app()` (lines 89–128)

### What it does

Builds a Starlette ASGI app with all A2A routes attached and run by uvicorn.

### How it does it

Three SDK components plug into each other:

```python
DefaultRequestHandler(
    agent_executor      = GreetingAgentExecutor(),   # YOUR business logic
    task_store          = InMemoryTaskStore(),       # state storage
    agent_card          = public_card,               # capability validation
    extended_agent_card = extended_card,             # for auth flow
)
```

| Component | Role |
|---|---|
| `DefaultRequestHandler` | The SDK's protocol-layer brain. Validates incoming JSON-RPC, manages task lifecycle, calls your executor, serializes events. |
| `InMemoryTaskStore` | A dict-backed store for task state. Real agents would use Redis/Postgres. |
| `GreetingAgentExecutor` | YOUR code. Implements the `AgentExecutor` interface. |

### Routes mounted

```python
create_agent_card_routes(public_card)   # GET /.well-known/agent-card.json
create_jsonrpc_routes(handler, "/")     # POST /  (all JSON-RPC methods)
```

That's it. Two endpoints, one for discovery, one for everything else.

---

## 5. Component 3 — The Executor

**File:** `greeting_agent/agent_executor.py` → `GreetingAgentExecutor.execute()` (lines 57–126)

### What it does

The bridge between the A2A protocol and your real logic. The SDK calls `execute()` for every incoming `message/send` or `message/stream` request.

### How it does it

It walks through the **A2A task lifecycle**, enqueueing one event at a time onto an `EventQueue`. The SDK serializes those events to SSE and pushes them to the client.

| Step | Event | Meaning |
|---|---|---|
| 1 | `Task` (SUBMITTED) | "I received your request — here's the task ID." |
| 2 | `TaskStatusUpdateEvent` (WORKING) | "I'm processing now." Includes a status message. |
| 3 | Extract name | Pull text from `context.message.parts` — A2A messages are arrays of typed parts (text/file/data). |
| 4 | Run logic | `self.agent.greet(name)` — the only "real" work. |
| 5 | `TaskArtifactUpdateEvent` | "Here's the result." Artifacts have a name + parts. |
| 6 | `TaskStatusUpdateEvent` (COMPLETED) | "Done." |

### Why split it this way?

`GreetingAgent.greet()` is plain Python — **no protocol leakage**. You could swap the protocol layer (REST, gRPC) without touching the business logic.

This is the **executor pattern** the A2A SDK enforces: protocol concerns live in the executor, business concerns live in a plain class.

### Cancellation

There's also `cancel()` for handling task cancellation — emits `TASK_STATE_CANCELED`.

---

## 6. Component 4 — The Client Flow

**File:** `client_agent/client.py` → `run_client()` (lines 62–188)

The client mirrors the server's lifecycle in **six steps**:

### Step 1 — Discovery (lines 74–87)

```python
resolver = A2ACardResolver(httpx_client, base_url=SERVER_BASE_URL)
card = await resolver.get_agent_card()
```

Fetches `/.well-known/agent-card.json` and parses it into a typed `AgentCard`. **No magic** — it's a GET + JSON parse + protobuf deserialization.

### Step 2 — Inspect capabilities (lines 90–107)

```python
streaming = card.capabilities.streaming
```

If `True`, the client picks **`message/stream`** (SSE). If `False`, **`message/send`** (synchronous). This is how A2A clients adapt to whatever the server supports.

### Step 3 — Build the client (lines 110–118)

```python
config  = ClientConfig(streaming=streaming, httpx_client=httpx_client)
client  = ClientFactory(config).create(card)
```

`ClientFactory` looks at `card.supported_interfaces`, picks a matching transport (here: JSON-RPC), and returns the right concrete client class. **You never pick the transport manually — the card decides.**

### Step 4 — Build the request (lines 121–133)

```python
message = Message()
message.message_id = str(uuid.uuid4())  # idempotency key
message.role       = Role.ROLE_USER
message.parts.add().text = name         # parts list — could be multi-modal

request = SendMessageRequest()
request.message.CopyFrom(message)
```

- `message_id` is for **idempotency** — re-sending the same ID is a no-op.
- `parts` is a list because messages can be multi-modal (text + image + JSON, etc.).

### Step 5 — Stream the response (lines 143–174)

```python
async for stream_response in client.send_message(request):
    if stream_response.HasField("task"): ...
    elif stream_response.HasField("status_update"): ...
    elif stream_response.HasField("artifact_update"): ...
    elif stream_response.HasField("message"): ...
```

`StreamResponse` is a **protobuf `oneof`** — exactly one of those four fields is set per chunk. The client dispatches on which field is present. This is how A2A multiplexes different event types over a single SSE stream.

The `HasField()` calls are a protobuf idiom (proto3 doesn't have null — you check field presence explicitly).

### Step 6 — Render

The final artifact's text is rendered in a `rich` panel.

---

## 7. Component 5 — The Orchestrator

**File:** `run_demo.py`

Glues everything together so you can run with one command.

### How it does it

1. **Background thread** runs uvicorn (lines 33–36) — daemon thread so it dies with the process.
2. **Health probe** (lines 39–50) — polls `/.well-known/agent-card.json` until 200 OK or 10s timeout. Avoids a race where the client connects before uvicorn has bound the port.
3. **Run client** in the main thread's asyncio loop (line 77).

### Why threading?

`uvicorn.run()` blocks. Running it in a thread lets the main thread proceed to the client. In production you'd run server and client as separate processes.

---

## 8. Wire-Level Trace

Here's exactly what flows between client and server when you run `python run_demo.py "Alice"`:

### Request 1 — Discovery

```
GET /.well-known/agent-card.json HTTP/1.1
Host: 127.0.0.1:9999

→ HTTP/1.1 200 OK
  Content-Type: application/json

  {
    "name": "Greeting Agent",
    "version": "1.0.0",
    "description": "A friendly A2A agent...",
    "capabilities": { "streaming": true, "extendedAgentCard": true },
    "supportedInterfaces": [
      { "protocolBinding": "JSONRPC", "url": "http://127.0.0.1:9999" }
    ],
    "skills": [{ "id": "greet", "name": "Greet a Person", ... }]
  }
```

### Request 2 — Task (JSON-RPC + SSE)

```
POST / HTTP/1.1
Host: 127.0.0.1:9999
Content-Type: application/json

{
  "jsonrpc": "2.0",
  "method":  "message/stream",
  "params": {
    "message": {
      "messageId": "550e8400-e29b-41d4-a716-446655440000",
      "role":      "USER",
      "parts":     [{ "text": "Alice" }]
    }
  }
}

→ HTTP/1.1 200 OK
  Content-Type: text/event-stream

  data: {"task": {"id": "abc-123", "status": {"state": "SUBMITTED"}}}

  data: {"statusUpdate": {"status": {"state": "WORKING",
                                       "message": {"parts": [{"text": "Executing..."}]}}}}

  data: {"artifactUpdate": {"artifact": {"name": "greeting_result",
                                          "parts": [{"text": "Hello, Alice! 👋..."}]}}}

  data: {"statusUpdate": {"status": {"state": "COMPLETED"}}}
```

That's the **entire A2A protocol** in this demo: discovery + JSON-RPC + SSE-streamed lifecycle events.

---

## 9. Separation of Concerns

| Layer | File | Concern |
|---|---|---|
| Identity | `build_agent_card()` | What this agent is + can do |
| Protocol | `DefaultRequestHandler` (SDK) | Validate, route, serialize |
| Lifecycle | `GreetingAgentExecutor.execute()` | Emit task events in order |
| Logic | `GreetingAgent.greet()` | Pure Python — no protocol |
| Discovery | `A2ACardResolver` | Fetch + parse card |
| Transport choice | `ClientFactory` | Pick JSON-RPC vs gRPC etc. |
| Stream consumer | `async for ... HasField()` | Dispatch on event type |

Each piece does **one thing**. The SDK enforces the contracts between them.

---

## 10. How to Run

### Option A — One command (recommended)

```powershell
# 1. Create a venv
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. Install dependencies
pip install a2a-sdk uvicorn starlette httpx rich

# 3. Run
python run_demo.py                  # greets "Siddharth"
python run_demo.py "Alice"          # custom name
```

### Option B — Separate terminals

Terminal 1 (server):
```powershell
python -m greeting_agent
```

Terminal 2 (client):
```powershell
python -m client_agent.client "Alice"
```

### What you'll see

1. Server boots on `http://127.0.0.1:9999`
2. Client fetches the Agent Card, prints capabilities and skills
3. Client sends the name as a `ROLE_USER` message
4. Stream events print in order: `task` → `status_update (WORKING)` → `artifact_update` → `status_update (COMPLETED)`
5. Final greeting renders in a green panel

---

## Mental Model

If you remember one thing: **A2A is just a typed contract over HTTP.** The SDK gives you the types and the plumbing. You write two things:

1. **An Agent Card** — declares what your agent does.
2. **An Executor** — runs your logic and emits lifecycle events.

Everything else (discovery, JSON-RPC, SSE, validation) is handled by the SDK.
