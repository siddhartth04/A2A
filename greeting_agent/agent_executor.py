"""
Greeting Agent Executor
-----------------------
Implements the official AgentExecutor interface from the a2a-sdk.

Flow:
  1. Enqueue the Task object (SUBMITTED)
  2. Enqueue TaskStatusUpdateEvent (WORKING)
  3. Execute greeting function
  4. Enqueue TaskArtifactUpdateEvent with result
  5. Enqueue TaskStatusUpdateEvent (COMPLETED)
"""

import uuid

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.types import (
    Artifact,
    Task,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
    Message,
    Role,
)


# ─── Core Business Logic ──────────────────────────────────────────────────────

class GreetingAgent:
    """
    The actual agent logic — completely decoupled from A2A protocol.
    In a real agent this would call an LLM, a database, an API, etc.
    """

    def greet(self, name: str) -> str:
        """Execute the greeting function and return the result."""
        name = name.strip() if name else "World"
        return f"Hello, {name}! 👋  Welcome to the A2A Protocol Demo."


# ─── A2A Executor ─────────────────────────────────────────────────────────────

class GreetingAgentExecutor(AgentExecutor):
    """
    Official AgentExecutor implementation using the a2a-sdk.

    The executor bridges the A2A protocol layer (managed by DefaultRequestHandler)
    and the agent's business logic (GreetingAgent).
    """

    def __init__(self) -> None:
        self.agent = GreetingAgent()

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """
        Called by the SDK for every message/send or message/stream request.
        Uses event_queue to stream protocol events back to the client.
        """

        # ── Step 1: Build and enqueue the Task (SUBMITTED state) ──────────
        task = Task()
        task.id = context.task_id
        task.context_id = context.context_id
        task.status.CopyFrom(TaskStatus(state=TaskState.TASK_STATE_SUBMITTED))

        # Copy user message into task history
        if context.message:
            task.history.add().CopyFrom(context.message)

        await event_queue.enqueue_event(task)

        # ── Step 2: Emit WORKING status ────────────────────────────────────
        working_msg = Message()
        working_msg.message_id = str(uuid.uuid4())
        working_msg.role = Role.ROLE_AGENT
        working_msg.parts.add().text = "Executing greeting function..."

        working_evt = TaskStatusUpdateEvent()
        working_evt.task_id = context.task_id
        working_evt.context_id = context.context_id
        working_evt.status.CopyFrom(
            TaskStatus(
                state=TaskState.TASK_STATE_WORKING,
                message=working_msg,
            )
        )
        await event_queue.enqueue_event(working_evt)

        # ── Step 3: Extract the name from the incoming message ─────────────
        name = "World"  # default
        if context.message:
            for part in context.message.parts:
                if part.HasField("text") and part.text.strip():
                    name = part.text.strip()
                    break

        # ── Step 4: Run the actual greeting logic ──────────────────────────
        greeting_result = self.agent.greet(name)

        # ── Step 5: Stream the Artifact ────────────────────────────────────
        artifact = Artifact()
        artifact.artifact_id = str(uuid.uuid4())
        artifact.name = "greeting_result"
        artifact.parts.add().text = greeting_result

        artifact_evt = TaskArtifactUpdateEvent()
        artifact_evt.task_id = context.task_id
        artifact_evt.context_id = context.context_id
        artifact_evt.artifact.CopyFrom(artifact)
        await event_queue.enqueue_event(artifact_evt)

        # ── Step 6: Emit COMPLETED status ──────────────────────────────────
        done_evt = TaskStatusUpdateEvent()
        done_evt.task_id = context.task_id
        done_evt.context_id = context.context_id
        done_evt.status.CopyFrom(
            TaskStatus(state=TaskState.TASK_STATE_COMPLETED)
        )
        await event_queue.enqueue_event(done_evt)

    async def cancel(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """Handle cancellation — emit CANCELLED state."""
        cancel_evt = TaskStatusUpdateEvent()
        cancel_evt.task_id = context.task_id
        cancel_evt.context_id = context.context_id
        cancel_evt.status.CopyFrom(
            TaskStatus(state=TaskState.TASK_STATE_CANCELED)
        )
        await event_queue.enqueue_event(cancel_evt)
