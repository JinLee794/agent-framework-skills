# Session State & Context Providers

## Pick the right layer first

"Memory" collapses three distinct concerns. Most bugs come from using the wrong one.

| Need | Use | Lifetime |
|---|---|---|
| Turn-to-turn context within one conversation | `AgentSession` | one conversation |
| Replayable local transcript | file history provider | one conversation, local disk |
| Agent-authored working notes/files | `FileMemoryProvider` (harness) | per working folder |
| Anything else injected before/after a run | custom `ContextProvider` | your choice |

Sessions are not retrieval. Grounding answers in a **document corpus** belongs in the existing
Azure AI Search service; see [retrieval.md](retrieval.md).

## Resource boundary

Cross-session cloud memory is intentionally unsupported. Foundry memory stores, Cosmos DB,
Redis, Mem0, and any other persistence service would add a resource or authentication path.
Keep runtime state in `AgentSession`; use file history only for local development and tests.

## Conversation history

For the transcript:

- `FileHistoryProvider(storage_directory, dumps=orjson.dumps)` — JSONL on disk; good for
  local development and replayable test fixtures.
- `InMemoryHistoryProvider()` — tests.

Use `default_options={"store": False}` because there is no project-backed service history.

## Custom context providers

```python
from typing import Any

from agent_framework import AgentSession, ContextProvider, SessionContext


class CallerContext(ContextProvider):
    DEFAULT_SOURCE_ID = "caller_context"

    async def before_run(
        self, *, agent: Any, session: AgentSession, context: SessionContext, state: dict[str, Any]
    ) -> None:
        if "profile" not in state:
            state["profile"] = await self._crm.lookup(context.session_id)
        context.instructions = f"Caller: {state['profile']['name']}, tier {state['profile']['tier']}."

    async def after_run(
        self, *, agent: Any, session: AgentSession, context: SessionContext, state: dict[str, Any]
    ) -> None:
        await self._crm.record_interaction(state["profile"]["id"], context)
```

- `source_id` must be unique per provider; state is keyed by it in `session.state`.
- Keep `before_run` fast. It is on the critical path of every turn — in a voice agent that is
  dead air on the line.
- `after_run` is the right place for slow writes — fire-and-forget or batch them.
- Providers compose: pass several in `context_providers=[...]`; they run in order.
- Context injected from another session is attributed via
  `Message.additional_properties["_attribution"]["origin_session_ids"]`.

## Harness file memory

`FileMemoryProvider` gives the agent `file_memory_write`, `file_memory_read`, and
`file_memory_grep` over an `AgentFileStore`. It is for agent-authored working notes, not user
facts. Keep its working folder local and out of production secrets.

## Voice-specific guidance

- Create one `AgentSession` per call and never share it across callers.
- Keep custom `before_run` providers fast; every lookup is audible latency.
- Never populate context identity or authorization fields from the spoken transcript.

## Anti-patterns

| Pattern | Verdict |
|---|---|
| Session shared across callers | Cross-conversation data leak |
| Slow I/O in `before_run` | Dead air on every turn |
| Cloud memory or persistence provider | Adds a forbidden resource; use session state or local test history |
| Document corpus in session state | Use the existing Azure AI Search service |
