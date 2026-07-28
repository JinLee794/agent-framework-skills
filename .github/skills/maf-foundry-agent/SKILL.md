---
name: maf-foundry-agent
description: "Building the reasoning agent: FoundryChatClient vs FoundryAgent, hosted tools, function tools, skills, MCP, memory, retrieval, sessions, middleware, hosting. Load for work under src/agents, src/tools, src/memory, src/retrieval. NOT for knowledge bases, knowledge sources, or Azure AI Search indexing — load foundry-iq for those."
license: MIT
compatibility: Python 3.10+; agent-framework + agent-framework-foundry; Foundry project endpoint.
metadata:
  author: MAFVoiceSeed
  version: "2.1.0"
  last-reviewed: "2026-07-28"
  verified-against: "agent-framework + agent-framework-foundry GA docs and python samples, 2026-07"
---

# MAF on Foundry — Agent Patterns

Depth lives in references. Load one only when the task needs it.

| Task | Reference |
|---|---|
| Write a `@tool`, author an Agent Skill, wire MCP, set approval modes | [references/tools-and-skills.md](references/tools-and-skills.md) |
| Cross-session memory, scoping, history, custom `ContextProvider` | [references/memory-and-context.md](references/memory-and-context.md) |
| Ground the agent in a document corpus — search, vector stores, file search | [references/retrieval.md](references/retrieval.md) |

Grounding in a **knowledge base** — Foundry IQ, knowledge sources, indexing, permission
trimming — is the separate `foundry-iq` skill.

## Install

```bash
python -m pip install agent-framework agent-framework-foundry
```

Everything Azure-AI-related lives in `agent_framework.foundry`:

```python
from agent_framework.foundry import (
    FoundryAgent, FoundryChatClient, FoundryEmbeddingClient, FoundryMemoryProvider,
    FoundryToolbox, InvocationsHostServer, ResponsesHostServer, to_prompt_agent,
)
```

## Decision: `FoundryChatClient` vs `FoundryAgent`

The first architectural choice, and frequently made wrong.

| | `Agent(client=FoundryChatClient(...))` | `FoundryAgent(...)` |
|---|---|---|
| Owns instructions / tools | your code | the Foundry agent definition |
| Runs the tool loop | Agent Framework, in-process | mixed: service picks, you may supply implementations |
| Add tools at construction | yes | no |
| Context providers | full support (inject context, add tools) | message injection and observation only |
| Hosted Foundry tools | yes, via factory methods | must be on the definition |
| Best for | apps that own their behaviour; dynamic tools; multi-agent | centrally governed, versioned agents |

Default to `FoundryChatClient`. Move to `FoundryAgent` only when the definition is managed in
Foundry and versioned independently of your code. `FoundryAgent` silently strips `tools`,
`instructions`, `model`, and `tool_choice` from run options — if you are passing those, you
picked the wrong class.

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

## Hosted Foundry tools — prefer these over custom HTTP

Factory methods on `FoundryChatClient`. They run in Foundry, are billed and traced there, and
need no code in your repo.

| Factory | Stage |
|---|---|
| `get_code_interpreter_tool()`, `get_file_search_tool()`, `get_web_search_tool()`, `get_image_generation_tool()`, `get_mcp_tool()` | GA |
| `get_bing_grounding_tool()`, `get_azure_ai_search_tool()` | experimental |
| `get_memory_search_tool()`, `get_sharepoint_tool()`, `get_fabric_tool()`, `get_bing_custom_search_tool()`, `get_computer_use_tool()`, `get_browser_automation_tool()`, `get_a2a_tool()` | preview |

Gate anything below GA behind a feature flag and state the stage in a code comment.

## Foundry toolboxes (experimental)

A project-level, reusable set of tools exposed over MCP; removes tool duplication across agents.

```python
from agent_framework import MCPStreamableHTTPTool
from azure.identity import DefaultAzureCredential, get_bearer_token_provider

token_provider = get_bearer_token_provider(
    DefaultAzureCredential(), "https://ai.azure.com/.default"
)
toolbox = MCPStreamableHTTPTool(
    name="foundry_toolbox",
    url=os.environ["FOUNDRY_TOOLBOX_ENDPOINT"],
    header_provider=lambda: {"Authorization": f"Bearer {token_provider()}"},
    load_prompts=False,
)
```

Endpoint shape:
`https://<account>.services.ai.azure.com/api/projects/<project>/toolsets/<name>/mcp?api-version=v1`

## Sessions and conversation state

```python
session = agent.create_session()                      # new conversation
session = agent.get_session(service_session_id=id)    # resume a service-side conversation
async for update in agent.run("...", session=session, stream=True):
    print(update.text, end="")
```

- One session per user conversation. Never share a session across users.
- **Authorize the session ID.** An ID from a client request is untrusted input; verify the
  caller owns it before resuming, or you have an IDOR.
- `session.to_dict()` / `AgentSession.from_dict()` for custom persistence; prefer service-side
  conversations when Foundry already stores them.
- In hosted agents the platform manages history — set `default_options={"store": False}` so
  the service does not persist a second copy.

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

## Publishing a prompt agent

Author locally, publish so voice topology A can reference it by name:

```python
from agent_framework.foundry import to_prompt_agent

definition = to_prompt_agent(agent)
created = await project_client.agents.create_version(agent_name="concierge", definition=definition)
```

Local `@tool` functions become declaration-only tools on the definition. Reconnect with
`FoundryAgent(agent_name=..., agent_version=..., tools=[cancel_booking])` to supply the
implementations — matching is by tool name.

## Hosting

| Server | Protocol | Use |
|---|---|---|
| `ResponsesHostServer(agent)` | OpenAI Responses | Foundry hosted agents; request/response |
| `InvocationsHostServer(agent)` | `invocations_ws` duplex | realtime/voice agents, streaming signaling |
| `AgentFunctionApp(agents=[...])` | HTTP via Azure Functions | serverless hosting |
| `devui ./entities` | local | development only — see [maf-dev-loop](../maf-dev-loop/SKILL.md) |

## Production credentials

`DefaultAzureCredential` probes many sources; in production that costs latency and can pick an
unintended identity. Use an explicit one:

```python
from azure.identity.aio import ManagedIdentityCredential
credential = ManagedIdentityCredential(client_id=os.environ["AZURE_CLIENT_ID"])
```

Reuse one credential and one `AIProjectClient` across chat, memory, and embeddings —
`client.project_client` is exposed on `FoundryChatClient` precisely so you can share it.

## Anti-patterns

| Pattern | Verdict |
|---|---|
| `AzureAIClient`, `AzureAIAgentClient`, `AzureAIAgentsProvider`, `AzureAIProjectAgentProvider` | Removed — use `agent_framework.foundry`. Match these names, not the `agent_framework.azure` namespace |
| `tools=` / `instructions=` passed to `FoundryAgent` | Silently stripped — you wanted `FoundryChatClient` |
| Agent constructed at module scope | Breaks DevUI reload; network at import |
| Missing `load_dotenv()` | Agent Framework does not load `.env` |
| Resuming a session ID straight from a client request | IDOR — authorize ownership first |
| A second `AIProjectClient` for memory or embeddings | Reuse `client.project_client` |
| `DefaultAzureCredential` in production | Latency + wrong-identity risk — name the identity |
