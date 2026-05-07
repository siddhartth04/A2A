"""
Greeting Agent — A2A Server
----------------------------
Uses the official a2a-sdk to expose:
  - GET  /.well-known/agent-card.json   (public Agent Card)
  - POST /                              (JSON-RPC endpoint for all A2A methods)

SDK classes used:
  - AgentSkill, AgentCard, AgentCapabilities, AgentInterface  → a2a.types
  - DefaultRequestHandler                                      → a2a.server.request_handlers
  - InMemoryTaskStore                                          → a2a.server.tasks
  - create_agent_card_routes, create_jsonrpc_routes            → a2a.server.routes
  - Starlette + uvicorn                                        → web server
"""

import uvicorn
from starlette.applications import Starlette

from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentInterface,
    AgentSkill,
)

from greeting_agent.agent_executor import GreetingAgentExecutor

HOST = "127.0.0.1"
PORT = 9999


def build_agent_card() -> AgentCard:
    """
    Define the public Agent Card — the agent's digital identity.
    Served at /.well-known/agent-card.json for discovery.
    """

    # ── Skill: what this agent can do ─────────────────────────────────────
    skill = AgentSkill(
        id="greet",
        name="Greet a Person",
        description=(
            "Takes a person's name as plain text and returns a personalised "
            "greeting message. Demonstrates the full A2A task lifecycle."
        ),
        tags=["greeting", "hello", "introduction", "demo"],
        examples=["Siddharth", "Alice", "Say hello to Bob"],
    )

    # ── Extended skill (only visible to authenticated clients) ────────────
    extended_skill = AgentSkill(
        id="greet_formal",
        name="Formal Greeting",
        description="Returns a formal greeting with title and full name.",
        tags=["greeting", "formal", "extended"],
        examples=["Dr. Siddharth Yadav", "Prof. Alice Smith"],
    )

    # ── Public Agent Card ─────────────────────────────────────────────────
    public_card = AgentCard(
        name="Greeting Agent",
        description=(
            "A friendly A2A agent that greets people by name. "
            "Built with the official a2a-sdk to demonstrate the full "
            "A2A protocol: Agent Card discovery, streaming, task lifecycle."
        ),
        version="1.0.0",
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        capabilities=AgentCapabilities(
            streaming=True,
            extended_agent_card=True,
        ),
        supported_interfaces=[
            AgentInterface(
                protocol_binding="JSONRPC",
                url=f"http://{HOST}:{PORT}",
            )
        ],
        skills=[skill],  # Public card shows basic skill only
    )

    return public_card, extended_skill, skill


def create_app() -> Starlette:
    """
    Build the Starlette app with all A2A routes attached.
    """
    public_card, extended_skill, basic_skill = build_agent_card()

    # Extended card — served to authenticated clients via agent/authenticatedExtendedCard
    extended_card = AgentCard(
        name="Greeting Agent — Extended",
        description="Full-featured greeting agent for authenticated clients.",
        version="1.0.0",
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        capabilities=AgentCapabilities(
            streaming=True,
            extended_agent_card=True,
        ),
        supported_interfaces=[
            AgentInterface(
                protocol_binding="JSONRPC",
                url=f"http://{HOST}:{PORT}",
            )
        ],
        skills=[basic_skill, extended_skill],  # Both skills
    )

    # ── Wire up the SDK components ─────────────────────────────────────────
    request_handler = DefaultRequestHandler(
        agent_executor=GreetingAgentExecutor(),   # Our business logic
        task_store=InMemoryTaskStore(),            # In-memory task state
        agent_card=public_card,                   # For capability validation
        extended_agent_card=extended_card,        # For authenticated clients
    )

    # ── Create routes ──────────────────────────────────────────────────────
    routes = []
    routes.extend(create_agent_card_routes(public_card))   # /.well-known/agent-card.json
    routes.extend(create_jsonrpc_routes(request_handler, "/"))  # JSON-RPC endpoint

    return Starlette(routes=routes)


if __name__ == "__main__":
    app = create_app()
    print(f"\n  Greeting Agent running at http://{HOST}:{PORT}")
    print(f"  Agent Card: http://{HOST}:{PORT}/.well-known/agent-card.json\n")
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")
