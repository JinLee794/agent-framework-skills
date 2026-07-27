# Memory & Context Providers

## Pick the right layer first

"Memory" collapses three distinct concerns. Most bugs come from using the wrong one.

| Need | Use | Lifetime |
|---|---|---|
| Turn-to-turn context within one conversation | `AgentSession` | one conversation |
| Durable transcript | history provider or a service-side conversation | one conversation, persisted |
| Facts about a user recalled across conversations | `FoundryMemoryProvider` | cross-session, per scope |
| Agent-authored working notes/files | `FileMemoryProvider` (harness) | per working folder |
| Anything else injected before/after a run | custom `ContextProvider` | your choice |

Sessions are not memory. Grounding answers in a **document corpus** is retrieval, not memory —
a memory store holds facts about the user; an index holds your content. See
[retrieval.md](retrieval.md).

## Foundry Memory — the default

Foundry-native, no extra datastore, shares the project's auth and RBAC.

```python
from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient, FoundryMemoryProvider

memory = FoundryMemoryProvider(
    project_client=client.project_client,   # reuse: one auth context, one connection pool
    memory_store_name=os.environ["FOUNDRY_MEMORY_STORE"],
    scope=user_id,
)

agent = Agent(
    client=client,
    instructions=(
        "Relevant memories from previous conversations are supplied in your context. "
        "Use them, and say when you are relying on a remembered fact."
    ),
    context_providers=[memory],
)
```

Constructor surface:

```python
FoundryMemoryProvider(
    source_id="foundry_memory",       # positional; unique per provider instance
    *,
    project_client=None,              # preferred: reuse client.project_client
    project_endpoint=None,            # only if you are not passing project_client
    credential=None,                  # required when project_client is None
    allow_preview=None,
    memory_store_name,                # REQUIRED, non-empty
    scope=None,                       # falls back to session_id
    context_prompt=None,
    update_delay=300,                 # seconds before memory update is processed
    env_file_path=None,
    env_file_encoding=None,
)
```

Per run: retrieves static user-profile memories on the first turn of a session, searches
contextual memories against the current user message, injects both, then updates the store
after the run.

### Scoping is a security boundary

`scope` isolates memories. Get it wrong and one user reads another's.

- Per-user recall: `scope=<stable user id>`. Never a display name or user-typed email.
- Session-only recall: leave `scope=None`; it falls back to `session_id`.
- Foundry hosted agents: `scope="{{$userId}}"` — the hosting layer substitutes the
  authenticated user id at runtime. Correct choice for multi-tenant hosted agents.

Never derive `scope` from unvalidated client input, and in a voice agent never from the
spoken transcript — a caller can say any name.

### `update_delay`

Defaults to `300` seconds, batching updates to reduce cost. Set `update_delay=0` only in
demos where you need to observe extraction immediately; it multiplies extraction calls.

### Provisioning the store

Provision in `infra/` or a one-time idempotent script; never inside request handling.

```python
from azure.ai.projects.aio import AIProjectClient
from azure.ai.projects.models import MemoryStoreDefaultDefinition, MemoryStoreDefaultOptions

definition = MemoryStoreDefaultDefinition(
    chat_model=os.environ["FOUNDRY_MODEL"],
    embedding_model=os.environ["FOUNDRY_EMBEDDING_MODEL"],
    options=MemoryStoreDefaultOptions(
        chat_summary_enabled=False,
        user_profile_enabled=True,
        user_profile_details=(
            "Avoid irrelevant or sensitive data, such as age, financials, "
            "precise location, and credentials"
        ),
    ),
)
await project_client.beta.memory_stores.create(
    name=os.environ["FOUNDRY_MEMORY_STORE"],
    description="Durable user-profile memory for the voice concierge.",
    definition=definition,
)
```

- Needs both a chat model and an embedding model deployed in the project.
- The caller needs the **Azure AI User** role on the project.
- Make the script re-runnable: catch the already-exists case and leave the store alone.
- `user_profile_details` is your PII guardrail. For real callers, state what must not be kept.
- Extraction is asynchronous. Do not assert a fact is recallable immediately after the turn
  that stated it.
- `memory_stores` lives under `project_client.beta` — treat the API as still-moving.

## Conversation history

Memory stores durable *facts*, not the transcript. For the transcript:

- Service-side conversations (Foundry) — default; nothing to manage.
- `FileHistoryProvider(storage_directory, dumps=orjson.dumps)` — JSONL on disk; good for
  local development and replayable test fixtures.
- `InMemoryHistoryProvider()` — tests.

To prove the agent relies on memory rather than transcript, disable both:
`default_options={"store": False}` plus `load_messages=False` on the history provider.

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
facts. Combine with `FoundryMemoryProvider` when the agent needs both.

## Non-Foundry alternatives

Use only with a stated reason — each adds a dependency, a datastore, and a second auth path.

| Provider | Package | Consider when |
|---|---|---|
| `Mem0ContextProvider` | `agent-framework-mem0` | already standardized on Mem0 |
| `CosmosMemoryContextProvider` | `agent-framework-azure-cosmos-memory` | need custom extraction prompts / direct Cosmos control |

## Voice-specific guidance

- Build the memory provider **once per call**, not per turn.
- Keep `update_delay` at its default; a voice turn cannot wait on memory extraction.
- Never let retrieved memories be spoken back verbatim; add a `context_prompt` instructing
  the model to acknowledge remembered facts naturally.

## Anti-patterns

| Pattern | Verdict |
|---|---|
| `scope` derived from a spoken name or client-supplied field | Cross-tenant leak — bind from authenticated identity |
| Memory store created inside request handling | Provision in `infra/` |
| `update_delay=0` in production | Multiplies extraction calls |
| Slow I/O in `before_run` | Dead air on every turn |
| Using a memory store to hold a document corpus | That is retrieval — use an index |
