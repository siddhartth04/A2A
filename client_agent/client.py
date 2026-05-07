"""
Client Agent — A2A Client
--------------------------
Uses the official a2a-sdk to:
  1. Fetch the Agent Card via A2ACardResolver
  2. Parse capabilities and print them
  3. Create a streaming client via ClientFactory
  4. Send a greeting request via SendMessageRequest
  5. Read the StreamResponse iterator and display results

SDK classes used:
  - A2ACardResolver     → fetches /.well-known/agent-card.json
  - ClientFactory       → creates A2A client from AgentCard
  - ClientConfig        → configures streaming / non-streaming
  - SendMessageRequest  → wraps the outgoing message
  - Message, Part, Role → build the message payload
  - StreamResponse      → each yielded chunk from send_message()
"""

import asyncio
import sys
import uuid

# Force UTF-8 stdout/stderr so rich's Unicode glyphs render on Windows consoles
# (default cp1252 cannot encode characters like ✓, ←, 👋).
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

import httpx
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text

from a2a.client import A2ACardResolver, ClientConfig, ClientFactory
from a2a.types import (
    Message,
    Part,
    Role,
    SendMessageRequest,
    TaskState,
)

console = Console()

SERVER_BASE_URL = "http://127.0.0.1:9999"


def print_step(num: int, title: str) -> None:
    console.print(f"\n[bold cyan][ STEP {num} ][/bold cyan]  [bold white]{title}[/bold white]")


def print_event(label: str, value: str, color: str = "green") -> None:
    console.print(f"  [dim]←[/dim]  [{color}]{label}[/{color}]  [white]{value}[/white]")


def print_result(text: str) -> None:
    console.print(
        Panel(
            Text(text, style="bold white", justify="center"),
            title="[bold green]✅  GREETING RESULT[/bold green]",
            border_style="green",
            padding=(1, 4),
        )
    )


async def run_client(name: str = "Siddharth") -> None:
    """
    Full A2A client flow using the official SDK.
    """
    console.print(Rule("[bold blue]  A2A GREETING DEMO — Official SDK  [/bold blue]"))
    console.print(f"  [dim]Server:[/dim]  {SERVER_BASE_URL}")
    console.print(f"  [dim]SDK:[/dim]     a2a-sdk v1.0.x  (Linux Foundation)")
    console.print(f"  [dim]Name:[/dim]    {name}\n")

    async with httpx.AsyncClient() as httpx_client:

        # ── STEP 1: Fetch the Agent Card ───────────────────────────────────
        print_step(1, "Fetching Agent Card via A2ACardResolver")
        console.print(f"  [dim]→[/dim]  GET {SERVER_BASE_URL}/.well-known/agent-card.json")

        resolver = A2ACardResolver(
            httpx_client=httpx_client,
            base_url=SERVER_BASE_URL,
        )
        card = await resolver.get_agent_card()

        console.print(f"  [dim]✓[/dim]  [green]Agent Name[/green]     :  {card.name}")
        console.print(f"  [dim]✓[/dim]  [green]Version[/green]        :  {card.version}")
        console.print(f"  [dim]✓[/dim]  [green]Description[/green]    :  {card.description[:60]}...")
        for iface in card.supported_interfaces:
            console.print(f"  [dim]✓[/dim]  [green]Endpoint[/green]       :  {iface.url}  [{iface.protocol_binding}]")

        # ── STEP 2: Read Capabilities ──────────────────────────────────────
        print_step(2, "Reading AgentCapabilities and Skills")

        streaming    = card.capabilities.streaming
        push_notifs  = card.capabilities.push_notifications
        ext_card     = card.capabilities.extended_agent_card

        console.print(f"  [dim]✓[/dim]  [yellow]streaming[/yellow]           :  {streaming}")
        console.print(f"  [dim]✓[/dim]  [yellow]push_notifications[/yellow]  :  {push_notifs}")
        console.print(f"  [dim]✓[/dim]  [yellow]extended_agent_card[/yellow] :  {ext_card}")
        console.print()

        for skill in card.skills:
            console.print(f"  [dim]✓[/dim]  [magenta]Skill[/magenta]  [{skill.id}]  {skill.name}")
            console.print(f"         [dim]{skill.description[:70]}[/dim]")
            console.print(f"         [dim]tags: {list(skill.tags)}[/dim]")

        mode = "message/stream (SSE)" if streaming else "message/send (sync)"
        console.print(f"\n  [dim]→[/dim]  Interaction pattern selected: [bold cyan]{mode}[/bold cyan]")

        # ── STEP 3: Create A2A Client ──────────────────────────────────────
        print_step(3, "Creating A2A Client via ClientFactory")

        config  = ClientConfig(streaming=streaming, httpx_client=httpx_client)
        factory = ClientFactory(config=config)
        client  = factory.create(card)

        console.print(f"  [dim]✓[/dim]  Client created: [green]{type(client).__name__}[/green]")
        console.print(f"  [dim]✓[/dim]  Transport:  [green]JSONRPC over HTTP[/green]")
        console.print(f"  [dim]✓[/dim]  Streaming:  [green]{streaming}[/green]")

        # ── STEP 4: Build the Message ──────────────────────────────────────
        print_step(4, f'Building SendMessageRequest  →  name = "{name}"')

        message = Message()
        message.message_id = str(uuid.uuid4())
        message.role       = Role.ROLE_USER
        message.parts.add().text = name

        request = SendMessageRequest()
        request.message.CopyFrom(message)

        console.print(f"  [dim]✓[/dim]  messageId  :  [dim]{message.message_id}[/dim]")
        console.print(f"  [dim]✓[/dim]  role       :  ROLE_USER")
        console.print(f"  [dim]✓[/dim]  content    :  \"{name}\"")

        # ── STEP 5: Send and Stream the Response ───────────────────────────
        print_step(5, "Sending request — reading StreamResponse events")
        console.print(f"  [dim]→[/dim]  POST {SERVER_BASE_URL}")
        console.print()

        greeting_text = None
        task_id = None

        async for stream_response in client.send_message(request):
            # StreamResponse has oneof: task | message | status_update | artifact_update

            if stream_response.HasField("task"):
                task = stream_response.task
                task_id = task.id
                state   = TaskState.Name(task.status.state)
                print_event("task", f"id={task_id[:8]}...  state={state}", "blue")

            elif stream_response.HasField("status_update"):
                evt   = stream_response.status_update
                state = TaskState.Name(evt.status.state)
                msg   = ""
                if evt.status.HasField("message"):
                    for p in evt.status.message.parts:
                        if p.HasField("text"):
                            msg = f'  "{p.text}"'
                            break
                print_event(f"status_update", f"{state}{msg}", "yellow")

            elif stream_response.HasField("artifact_update"):
                evt = stream_response.artifact_update
                for part in evt.artifact.parts:
                    if part.HasField("text"):
                        greeting_text = part.text
                        print_event("artifact_update", f'name="{evt.artifact.name}"  text="{greeting_text}"', "green")

            elif stream_response.HasField("message"):
                for p in stream_response.message.parts:
                    if p.HasField("text"):
                        greeting_text = p.text
                print_event("message", greeting_text or "(empty)", "cyan")

        # ── STEP 6: Display Final Result ───────────────────────────────────
        console.print()
        console.print(Rule("[bold green]  Result  [/bold green]"))

        if greeting_text:
            print_result(greeting_text)
        else:
            console.print("  [red]No greeting received.[/red]")

        if task_id:
            console.print(f"\n  [dim]Task ID  :  {task_id}[/dim]")

        console.print(Rule())


if __name__ == "__main__":
    import sys
    name = sys.argv[1] if len(sys.argv) > 1 else "Siddharth"
    asyncio.run(run_client(name))
