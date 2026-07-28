# Wiring — Four Ways to Consume a Knowledge Base

Pick one. Mixing paths in a single agent means two different auth models and two different
result shapes for the same corpus.

| Path | Use when | Per-caller trimming |
|---|---|---|
| **A. MAF context provider** | Topology B/C. Every turn should be grounded | Yes, via `filter_add_on` |
| **B. Direct `retrieve` as a `@tool`** | Retrieval is occasional, or you need per-caller tokens and interim voice responses | Yes, fully |
| **C. Foundry Agent Service + MCP tool** | Topology A. Agent is defined and hosted in Foundry | **No** (preview limitation) |
| **D. Responses API + MCP tool** | You call the model directly and need per-request headers | Yes |

## A. `AzureAISearchContextProvider` — the repo default

```python
from agent_framework.azure import AzureAISearchContextProvider

async with AzureAISearchContextProvider(
    endpoint=os.environ["AZURE_SEARCH_ENDPOINT"],
    credential=credential,
    mode="agentic",
    knowledge_base_name=os.environ["AZURE_SEARCH_KNOWLEDGE_BASE_NAME"],
    top_k=3,
) as search:
    agent = chat_client.create_agent(
        instructions=cfg.instructions,
        context_providers=search,
    )
```

Constraints that bite:

- Supply **exactly one** of `knowledge_base_name` or `index_name`. Both is an error.
- With `index_name`, the provider **auto-creates** a knowledge base called `<index_name>-kb`,
  and then requires `azure_openai_resource_url` + `model`. That URL is the **Azure OpenAI
  resource URL**, not the Foundry project endpoint — this is the single most common wiring
  mistake. Prefer creating the base in `infra/` and passing `knowledge_base_name`.
- The provider owns a client. Use `async with`, or call `await search.close()`. Leaking it
  leaks sockets across a long-lived voice session.
- `knowledge_base_output_mode="answer_synthesis"` and `retrieval_reasoning_effort` of
  `low`/`medium` require the **preview** `azure-search-documents` build. The stable build
  supports `extractive_data` and `minimal` only, and fails at call time, not at construction.
- Agentic mode sends only the last `agentic_message_history_count` messages (default 10) as
  retrieval context. In a long voice call, an entity mentioned 30 turns ago is invisible to the
  planner — restate it in the query or carry it in memory.

Bind `top_k`, effort, and instructions from `config/**.yaml`, never as literals.

## B. Direct `retrieve` as a function tool

Best for voice: you control when it runs, you can speak an interim response while it runs, and
you can forward the caller's token.

```python
from agent_framework import tool

@tool
async def search_policies(query: str) -> str:
    """Search internal policy documents. Use for questions about leave, benefits, or conduct."""
    result = await retrieval_client.retrieve(
        knowledge_base_name=kb_name,
        retrieval_request=KnowledgeBaseRetrievalRequest(
            messages=[KnowledgeRetrievalSemanticIntent(role="user", content=query)],
        ),
        x_ms_query_source_authorization=session.user_search_token,   # from the AUTHENTICATED session
    )
    return result.response[0].content[0].text
```

The docstring is the routing prompt — the model decides from it alone. Name the domain and the
question types, not the backend.

`x_ms_query_source_authorization` must come from the authenticated session context. Never from
a transcript, a tool argument, or anything the caller can influence.

## C. Foundry Agent Service — project connection + MCP tool

Two steps. The connection is infrastructure; the tool is agent definition.

**1. Project connection** (ARM, `2025-10-01-preview`):

```http
PUT https://management.azure.com{project_resource_id}/connections/{name}?api-version=2025-10-01-preview
```

```json
{
  "properties": {
    "authType": "ProjectManagedIdentity",
    "category": "RemoteTool",
    "target": "{search_endpoint}/knowledgebases/{kb}/mcp?api-version=2026-05-01-preview",
    "isSharedToAll": true,
    "audience": "https://search.azure.com/",
    "metadata": { "ApiType": "Azure" }
  }
}
```

The project's system-assigned managed identity needs **Search Index Data Reader** on the search
service. `audience` must be exactly `https://search.azure.com/` — a wrong audience surfaces as
a generic `401` from the MCP endpoint.

**2. Attach the tool:**

```python
from azure.ai.projects.models import MCPTool, PromptAgentDefinition

mcp_kb_tool = MCPTool(
    server_label="knowledge-base",
    server_url=os.environ["AZURE_SEARCH_MCP_ENDPOINT"],
    require_approval="never",
    allowed_tools=["knowledge_base_retrieve"],
    project_connection_id=os.environ["FOUNDRY_KB_CONNECTION_NAME"],
)

agent = project_client.agents.create_version(
    agent_name=agent_name,
    definition=PromptAgentDefinition(
        model=agent_model,
        instructions=cfg.instructions,
        tools=[mcp_kb_tool],
    ),
)
```

- `knowledge_base_retrieve` is the **only** MCP tool Foundry Agent Service supports here. Always
  set `allowed_tools`; leaving it open lets the agent attempt tools that will fail.
- Result shape differs from REST: `result.content[]` entries of `type: "text"` carrying a
  JSON-encoded grounding string. There is **no `activity` and no `references` array**. Any code
  that renders citations from `references` must be written against path A, B, or D.
- **No per-request headers.** Headers set on the definition apply to every invocation, so you
  cannot pass a per-caller token. If the corpus needs per-user trimming, this path is
  disqualified — use B or D.
- Citation URLs vary: blob-backed sources return the original document URL; index-backed
  sources fall back to the MCP endpoint, which is not a useful link for a user.
- Deleting the agent or the connection deletes **neither** the knowledge base nor its sources.

## D. Responses API + MCP tool

The path that does support per-request headers.

```python
response = client.responses.create(
    model=deployment,
    input=user_message,
    tools=[{
        "type": "mcp",
        "server_label": "knowledge-base",
        "server_url": mcp_endpoint,
        "allowed_tools": ["knowledge_base_retrieve"],
        "headers": {"Authorization": f"Bearer {search_token_provider()}"},
        "require_approval": "never",
    }],
)
```

Use an Entra token, scope `https://search.azure.com/.default`. Admin keys in an `api-key`
header work for local dev and should never reach a deployed environment.

## Instructions that actually cause retrieval

An attached knowledge base the model never calls is the most common "Foundry IQ doesn't work"
report. In `config/agent.yaml`:

```yaml
instructions: |
  You answer questions about {{ runtime.domain }} using the connected knowledge base.

  - Search the knowledge base before answering any factual question about our
    policies, products, or procedures. Do not answer from prior knowledge.
  - If the search returns nothing relevant, say you could not find it. Do not guess.
  - Cite the document title for every fact you state.
  - Rewrite the caller's question into a specific search query before searching;
    do not pass filler or greetings to the tool.
```

Then verify with `include_activity=True` that the tool is being called at all before tuning
anything else.

## Voice specifics

- **Say something before you search.** A retrieve with planning can exceed the silence a caller
  will tolerate. Emit an interim response, then speak the result. See
  [voicelive-realtime](../../voicelive-realtime/SKILL.md).
- **`minimal` effort in the turn path.** `low` and `medium` add a planning round trip per turn.
- **Never answer synthesis in voice.** Synthesized prose reads as a wall of text aloud.
  Retrieve extracted data and let the voice agent phrase it in one or two sentences.
- **Cite by title, not URL.** Reading a blob URL aloud is unusable.
- **Barge-in must cancel the retrieve.** Otherwise a stale answer arrives after the caller has
  moved on. Tie the task to the turn's cancellation scope.

## Result handling

Retrieved content is **untrusted input**. A document in the corpus can contain instructions.
Never let retrieved text change tool selection, identity, memory `scope`, or filters. Treat it
strictly as content to quote and cite.
