---
name: maf-foundry-agent
description: "Building the local MAF reasoning agent against a Microsoft Foundry project endpoint: agent factories, function tools, skills, sessions, middleware, and Azure AI Search retrieval. Load for work under src/agents, src/tools, or src/retrieval. NOT for chunking, embedding, populating, or inspecting a Search index - load foundry-iq for that."
license: MIT
compatibility: Python 3.10+; agent-framework + agent-framework-foundry; Microsoft Foundry project endpoint; azure-identity.
metadata:
  author: MAFVoiceSeed
  version: "2.3.0"
  last-reviewed: "2026-07-29"
  verified-against: "agent-framework + agent-framework-foundry GA docs and Python samples, 2026-07"
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
python -m pip install agent-framework agent-framework-foundry azure-identity
```

Use the Foundry client against the existing project endpoint:

```python
from agent_framework.foundry import FoundryChatClient
```

`FoundryChatClient` requires a token credential for the project endpoint. Use
`AzureCliCredential` locally and inject a deliberate token credential in deployment. The local
MAF `Agent` still owns instructions, tools, sessions, and middleware.

## Baseline agent

Instructions, model, and the tool list come from `config/agents/<name>.agent.yaml` — see
[maf-agent-config](../maf-agent-config/SKILL.md). The code below is what the config builder
produces. Do not write literal instructions or tool lists into `src/`.

```python
import os

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv

load_dotenv()  # Agent Framework never does this for you


def build_concierge_agent(client: FoundryChatClient, **deps) -> Agent:
    return Agent(client=client, name="concierge", instructions=..., tools=[...])


async def main() -> None:
  async with AzureCliCredential() as credential:
    client = FoundryChatClient(
      project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
      model=os.environ["FOUNDRY_MODEL"],
      credential=credential,
    )
    agent = build_concierge_agent(client)
    session = agent.create_session()
    print(await agent.run("Do I have a booking under ABC123?", session=session))
```

Always export a `build_<name>_agent(client, **deps) -> Agent` factory. It is what lets the
voice loop, DevUI, and tests mount the *same* agent. Module-level construction breaks DevUI
reload and forces network access at import time.

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

Three kinds, all composable, same shape (receive context, `await next(context)`):

| Kind | Context | Typical use |
|---|---|---|
| Agent | `AgentContext` | auth, rate limiting, request/response logging, termination |
| Function | `FunctionInvocationContext` | tool-level approval, arg validation, retries |
| Chat | `ChatContext` | prompt shaping, model fallback, token accounting |

```python
from agent_framework import agent_middleware, AgentContext

@agent_middleware
async def require_tenant(context: AgentContext, next):
    if not context.metadata.get("tenant_id"):
        context.terminate("Missing tenant.")
        return
    await next(context)
```

Order is outside-in then inside-out: `A1 → A2 → F1 → F2 → agent → F2 → F1 → A2 → A1`.
Skipping `await next(context)` is the supported way to deny a request.

## Agents as tools

```python
researcher_tool = researcher.as_tool(
    name="research", description="Research a topic and return a summary",
    arg_name="query", arg_description="What to research",
)
coordinator = Agent(client=client, instructions="Delegate research.", tools=[researcher_tool])
```

Prefer this over hand-rolled orchestration for simple delegation. Reach for Workflows only
when you need graph structure, checkpointing, or human-in-the-loop gates.

## Credential handling

The project endpoint does not accept the Foundry resource API key through
`FoundryChatClient`. Inject a token credential into the client factory and never derive
identity from a request or transcript. Keep `.env` gitignored.

## Anti-patterns

| Pattern | Verdict |
|---|---|
| API key passed to `FoundryChatClient` / `AIProjectClient` | Project clients require a token credential |
| Agent constructed at module scope | Breaks DevUI reload; network at import |
| Missing `load_dotenv()` | Agent Framework does not load `.env` |
| Resuming a session ID straight from a client request | IDOR — authorize ownership first |
| Credential or key embedded in code, YAML, or a tool argument | Inject it at the client boundary |
| Project connection, memory store, App Insights, Storage, Cosmos DB, Redis, or Content Understanding | Adds a forbidden resource or auth path |
