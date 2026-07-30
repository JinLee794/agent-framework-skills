---
name: maf-foundry-agent
description: "Building the local MAF reasoning agent against a Microsoft Foundry project endpoint: agent factories, function tools, skills, sessions, middleware, and Azure AI Search retrieval. Load for work under src/agents, src/tools, or src/retrieval. NOT for chunking, embedding, populating, or inspecting a Search index - load foundry-iq for that."
license: MIT
compatibility: Python 3.10+; agent-framework + agent-framework-foundry; Microsoft Foundry project endpoint; azure-identity.
metadata:
  author: MAFVoiceSeed
  version: "2.4.0"
  last-reviewed: "2026-07-29"
  verified-against: "agent-framework 1.12.1 installed source (symbols and signatures introspected); Microsoft Learn Foundry auth + OpenAI v1 API docs, 2026-07"
---

# MAF on Foundry — Agent Patterns

Depth lives in references. Load one only when the task needs it.

| Task | Reference |
|---|---|
| Write a `@tool`, author an Agent Skill, set approval modes | [references/tools-and-skills.md](references/tools-and-skills.md) |
| Session history and custom `ContextProvider` | [references/memory-and-context.md](references/memory-and-context.md) |
| Ground the agent in Azure AI Search | [references/retrieval.md](references/retrieval.md) |

Creating, populating, and validating the Azure AI Search index is owned by the separate
`foundry-iq` skill.

## Install

```bash
python -m pip install agent-framework agent-framework-foundry agent-framework-declarative azure-identity
```

## Choose the chat client by credential

Pick the client from the credential you actually hold. Getting this wrong surfaces as a `403`
on the *first model call*, long after startup looked healthy.

| You have | Client | Endpoint |
|---|---|---|
| Entra token **and** `Foundry User` on the resource | `FoundryChatClient` | project endpoint |
| Resource API key only | `OpenAIChatClient` | `<resource>/openai/v1/` |

`FoundryChatClient` takes `credential: AzureCredentialTypes | AzureTokenProvider` — there is no
`api_key` parameter, so a key cannot be substituted. The same holds for `AIProjectClient`,
whose second positional parameter is an `AsyncTokenCredential`. A missing role assignment
surfaces as `403 Forbidden`; `Owner` is not enough, because model and agent calls are data
actions. Assign the built-in `Foundry User` role at resource or project scope.

```python
# Entra: project endpoint
from agent_framework.foundry import FoundryChatClient

client = FoundryChatClient(
    project_endpoint=settings.foundry_project_endpoint,
    model=config.model.deployment,
    credential=credential,
)
```

```python
# API key only: resource endpoint
from agent_framework.openai import OpenAIChatClient

client = OpenAIChatClient(
    config.model.deployment,
    api_key=settings.foundry_api_key,
    base_url=settings.foundry_openai_base_url,  # <resource>/openai/v1/
)
```

The key path must use a `base_url` ending in `/openai/v1/`. Agent Framework calls the Responses
API, and pairing `azure_endpoint=` with a dated `api_version` fails with
`400 API version not supported`. Derive the resource endpoint by stripping `/api/projects/...`
from the project endpoint. Credentials accepted by the VoiceLive websocket are owned by
[voicelive-realtime](../voicelive-realtime/SKILL.md).

Annotate factories and builders as `BaseChatClient` so either client mounts unchanged.

## Baseline agent

Instructions, model, and the tool list come from `config/agents/<name>.yaml`, a MAF-native
`kind: Prompt` document — see [maf-agent-config](../maf-agent-config/SKILL.md). Do not write
literal instructions or tool lists into `src/`, and do not hand-roll a parser for that
document: `AgentFactory` already does it.

```python
from pathlib import Path
from typing import Any

from agent_framework import Agent, BaseChatClient, ContextProvider
from agent_framework.declarative import AgentFactory

CONFIG_PATH = Path("config/agents/concierge.yaml")


def build_concierge_agent(client: BaseChatClient, **deps: Any) -> Agent:
    factory = AgentFactory(
        client=client,
        bindings=deps["tool_bindings"],
        safe_mode=False,
    )
    agent = factory.create_agent_from_yaml_path(CONFIG_PATH)
    providers: list[ContextProvider] = list(deps.get("context_providers", ()))
    agent.context_providers.extend(providers)
    return agent
```

The factory signature is fixed: `build_<name>_agent(client, **deps) -> Agent`. Taking the
client as a parameter is what lets the voice loop, DevUI, and tests mount the *same* agent
against different clients. Module-level construction breaks DevUI reload and forces network
access at import time. `load_dotenv()` belongs at the process entry point, never here.

`AgentFactory` returns a plain `Agent`. Retrieval providers are attached afterwards:
`agent.context_providers` is a mutable `list` even when the document declared none, so
`.extend(...)` is safe. `agent.middleware` is **not** — it is `None` unless middleware was
passed to the constructor, so pass middleware in at construction rather than appending to it.
`create_agent_from_yaml_path` is sync; `create_agent_from_yaml_path_async` exists for async
call sites and is preferred inside the voice loop's setup.

A declared `function` tool whose binding name is missing from `bindings` is constructed with
`func=None` and fails silently at call time. Assert the mapping is total when you build.

## Entry point

`load_dotenv()` is called **once**, at the process entry point — Agent Framework never loads
`.env` for you. Credentials and clients are async context managers; leaking them leaks
connections.

```python
import asyncio
import os

from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv


async def main() -> None:
    load_dotenv()
    async with AzureCliCredential() as credential:
        client = FoundryChatClient(
            project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
            model=os.environ["FOUNDRY_MODEL_DEPLOYMENT"],
            credential=credential,
        )
        agent = build_concierge_agent(client, tool_bindings=TOOL_BINDINGS)
        session = agent.create_session()
        print(await agent.run("Do I have a booking under ABC123?", session=session))


asyncio.run(main())
```

## Supported capabilities

- Local `@tool` functions and Agent Skills.
- Local middleware and multi-agent composition.
- Azure AI Search context providers and direct retrieval using `AZURE_SEARCH_API_KEY`.
- `AgentSession` for per-conversation state.

Project toolboxes, hosted tools, Foundry memory stores, project connections, and hosted agents
are outside the resource and authentication contract.

## Sessions and conversation state

```python
from agent_framework import AgentSession

session = agent.create_session()
async for update in agent.run("...", session=session, stream=True):
    print(update.text, end="")

serialized = session.to_dict()
session = AgentSession.from_dict(serialized)
```

- One session per user conversation. Never share a session across users.
- **Authorize resumed state.** A serialized session handle from a client request is untrusted;
  verify the authenticated caller owns it before restoring, or you have an IDOR.
- Keep session persistence in application-owned storage only if the application already has
  it. This seed does not provision a session database.

## Middleware

Three kinds, all composable, same shape. The handler receives its context and a **zero-arg**
`next` — the signature is `Callable[[Context, Callable[[], Awaitable[None]]], Awaitable[None]]`,
so it is `await next()`, never `await next(context)`.

| Kind | Decorator | Context | Typical use |
|---|---|---|---|
| Agent | `@agent_middleware` | `AgentContext` | auth, rate limiting, request/response logging, termination |
| Function | `@function_middleware` | `FunctionInvocationContext` | tool-level approval, arg validation, retries |
| Chat | `@chat_middleware` | `ChatContext` | prompt shaping, model fallback, token accounting |

```python
from collections.abc import Awaitable, Callable

from agent_framework import AgentContext, MiddlewareTermination, agent_middleware


@agent_middleware
async def require_tenant(
    context: AgentContext, next: Callable[[], Awaitable[None]]
) -> None:
    if not context.metadata.get("tenant_id"):
        raise MiddlewareTermination("Missing tenant.")
    await next()
```

Order is outside-in then inside-out: `A1 → A2 → F1 → F2 → agent → F2 → F1 → A2 → A1`.
To deny a request, either return without awaiting `next()` or raise `MiddlewareTermination`,
which carries an optional `result=` used as the response. `context.metadata` is populated by
the host from the *authenticated* session — never from a transcript.

## Agents as tools

```python
researcher_tool = researcher.as_tool(
    name="research", description="Research a topic and return a summary",
    arg_name="query", arg_description="What to research",
)
coordinator = build_coordinator_agent(client, tools=[researcher_tool])
```

`as_tool` defaults to `approval_mode="never_require"` and `propagate_session=False`. Raise the
approval mode if the delegate can cause side effects. The coordinator's own instructions still
come from its `kind: Prompt` document, not from a literal in `src/`.

Prefer this over hand-rolled orchestration for simple delegation. Anything beyond one
delegated call — a second participant, an orchestration pattern, graph structure,
checkpointing, or human-in-the-loop gates — is
[maf-multi-agent-workflows](../maf-multi-agent-workflows/SKILL.md).

## Credential handling

The project endpoint does not accept the Foundry resource API key through
`FoundryChatClient`. Inject a token credential into the client factory and never derive
identity from a request or transcript. Keep `.env` gitignored.

## Anti-patterns

| Pattern | Verdict |
|---|---|
| A hand-rolled parser for `config/agents/*.yaml` | `AgentFactory` already loads that schema |
| A `function` tool declared in YAML with no entry in `bindings` | Built with `func=None`; the model calls a no-op |
| API key passed to `FoundryChatClient` / `AIProjectClient` | Neither has an `api_key` parameter; they require a token credential |
| `await next(context)` in middleware | `next` is zero-arg; this raises `TypeError` |
| `context.terminate(...)` | Not an API. Return early or raise `MiddlewareTermination` |
| `agent.middleware.append(...)` | `middleware` is `None` unless passed to the constructor |
| Agent constructed at module scope | Breaks DevUI reload; network at import |
| `load_dotenv()` missing, or called from a library module | Agent Framework does not load `.env`; call it once at the entry point |
| Client or credential created without `async with` / `close()` | Leaks connections |
| Resuming a session ID straight from a client request | IDOR — authorize ownership first |
| Credential or key embedded in code, YAML, or a tool argument | Inject it at the client boundary |
| Identity, tenant, or filter read from the transcript | The caller is untrusted input; bind from the authenticated session |
| Project connection, memory store, App Insights, Storage, Cosmos DB, Redis, or Content Understanding | Adds a forbidden resource or auth path |
