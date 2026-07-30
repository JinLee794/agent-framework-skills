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

- `FileHistoryProvider(storage_path, dumps=orjson.dumps)` — JSONL on disk; good for
  local development and replayable test fixtures. The first parameter is `storage_path`
  (`str | Path`), not `storage_directory`.
- `InMemoryHistoryProvider()` — tests.

Use `default_options={"store": False}` because there is no project-backed service history.

## Custom context providers

```python
from typing import Any

from agent_framework import AgentSession, ContextProvider, SessionContext


class CallerContext(ContextProvider):
    def __init__(self, crm: CrmClient, *, caller_id: str) -> None:
        super().__init__("caller_context")  # source_id is a required positional argument
        self._crm = crm
        self._caller_id = caller_id  # from the authenticated session, never the transcript

    async def before_run(
        self, *, agent: Any, session: AgentSession, context: SessionContext, state: dict[str, Any]
    ) -> None:
        if "profile" not in state:
            state["profile"] = await self._crm.lookup(self._caller_id)
        profile = state["profile"]
        context.extend_instructions(
            self.source_id,
            f"Caller: {profile['name']}, tier {profile['tier']}.",
        )

    async def after_run(
        self, *, agent: Any, session: AgentSession, context: SessionContext, state: dict[str, Any]
    ) -> None:
        await self._crm.record_interaction(state["profile"]["id"], context)
```

- `ContextProvider.__init__` takes `source_id` as a **required positional argument**. A
  subclass that forgets `super().__init__(...)` fails at construction; there is no
  `DEFAULT_SOURCE_ID` class attribute to fall back on.
- `SessionContext.instructions` is a `list[str]`. Assigning a string to it is a type error that
  also silently discards every other provider's contribution — call
  `context.extend_instructions(self.source_id, ...)`. Use `context.extend_messages(...)` for
  anything untrusted, such as retrieved documents, so it never gains system authority.
- `source_id` must be unique per provider; state is keyed by it.
- Keep `before_run` fast. It is on the critical path of every turn — in a voice agent that is
  dead air on the line.
- `after_run` is the right place for slow writes — fire-and-forget or batch them.
- Providers compose: pass several in `context_providers=[...]`; they run in order.
- Context injected from another session is attributed through
  `Message.additional_properties`; check the attribution payload on your installed version
  before relying on its exact shape.

## Harness file memory

`FileMemoryProvider` gives the agent file tools over an `AgentFileStore` — `file_memory_read`,
`file_memory_ls`, `file_memory_grep`, plus write, replace, and delete variants. It is
experimental, and it is for agent-authored working notes, not user facts. Keep its working
folder local and out of production secrets.

## Voice-specific guidance

- Create one `AgentSession` per call and never share it across callers.
- Keep custom `before_run` providers fast; every lookup is audible latency.
- Never populate context identity or authorization fields from the spoken transcript.

## Anti-patterns

| Pattern | Verdict |
|---|---|
| Session shared across callers | Cross-conversation data leak |
| Slow I/O in `before_run` | Dead air on every turn |
| `context.instructions = "..."` | It is a `list[str]`; use `extend_instructions(source_id, ...)` |
| `ContextProvider` subclass without `super().__init__(source_id)` | `source_id` is required and positional |
| Identity or authorization field populated from the transcript | The caller is untrusted input |
| Cloud memory or persistence provider | Adds a forbidden resource; use session state or local test history |
| Document corpus in session state | Use the existing Azure AI Search service |
