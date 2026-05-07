"""
run_demo.py — A2A Two-Agent Greeting Demo
------------------------------------------
Starts the Greeting Agent server in a background thread,
waits for it to be ready, then runs the client.

Usage:
    python run_demo.py                   # greets "Siddharth"
    python run_demo.py "Your Name"       # greets your name
"""

import asyncio
import sys
import threading
import time

import httpx
import uvicorn
from rich.console import Console
from rich.rule import Rule

# ── Import server and client ──────────────────────────────────────────────────
sys.path.insert(0, "")

from greeting_agent.__main__ import create_app, HOST, PORT
from client_agent.client import run_client

console = Console()

SERVER_URL = f"http://{HOST}:{PORT}"


def start_server() -> None:
    """Run the Starlette/uvicorn server in a background thread."""
    app = create_app()
    uvicorn.run(app, host=HOST, port=PORT, log_level="error")


def wait_for_server(timeout: int = 10) -> bool:
    """Poll until the server is ready or timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            resp = httpx.get(f"{SERVER_URL}/.well-known/agent-card.json", timeout=1)
            if resp.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(0.3)
    return False


if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else "Siddharth"

    console.print(Rule("[bold blue]  A2A Two-Agent Greeting Demo  [/bold blue]"))
    console.print("  [dim]Protocol:[/dim]  Agent2Agent (A2A) v1.0  —  Official SDK")
    console.print("  [dim]Author:[/dim]   Siddharth Yadav")
    console.print("  [dim]Stack:[/dim]    a2a-sdk · Starlette · uvicorn · httpx")
    console.print()

    # ── Start server ──────────────────────────────────────────────────────
    console.print("  [yellow]▶[/yellow]  Starting Greeting Agent server...")
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()

    # ── Wait for server to be ready ───────────────────────────────────────
    ready = wait_for_server()
    if not ready:
        console.print("  [red]✗  Server did not start in time.[/red]")
        sys.exit(1)

    console.print(f"  [green]✓[/green]  Server ready at [bold]{SERVER_URL}[/bold]")
    console.print()

    # ── Run client ────────────────────────────────────────────────────────
    asyncio.run(run_client(name))
