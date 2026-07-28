# RAG & Retrieval

Retrieval grounds answers in a **document corpus**. Recalling facts about the *user* is
memory — see [memory-and-context.md](memory-and-context.md). Conflating them produces agents
that "remember" documents and "retrieve" user facts, and both degrade.

## Choose a strategy

| Strategy | Where retrieval runs | Pick when |
|---|---|---|
| **Hosted `file_search`** over a Foundry vector store | Foundry service | Corpus is files you can upload. Zero infrastructure. **Start here.** |
| **`AzureAISearchContextProvider`, `mode="semantic"`** | your process, before each run | You already own an Azure AI Search index. **Default for voice.** |
| **`AzureAISearchContextProvider`, `mode="agentic"`** | Azure AI Search Knowledge Base | Multi-hop or comparative questions worth extra latency |
| **`get_azure_ai_search_tool()`** (experimental) | Foundry service | Index queried service-side via a project connection, on the model's initiative |
| **Content Understanding + `file_search`** | CU then vector store | Scanned PDFs, audio, video, 100+ page documents |

Anything involving a **knowledge base** — creating one, wiring knowledge sources, indexing,
re-indexing, permission trimming, the MCP endpoint, or the Foundry portal flow — is the
`foundry-iq` skill. This file covers only how MAF consumes retrieval; `foundry-iq` covers how
the corpus gets there and how it is secured.

Two axes decide most cases:

- **Always-on vs on-demand.** A context provider retrieves before *every* run whether the
  question needs it or not — predictable, fixed latency. A tool retrieves only when the model
  chooses — cheaper, but sometimes skipped.
- **Who owns the index.** Foundry owns it → hosted `file_search`. Azure AI Search owns it →
  the context provider.

## Hosted file search (GA, start here)

```python
openai_client = client.client  # OpenAI-compatible async client — reuse it

vector_store = await openai_client.vector_stores.create(
    name="product-docs",
    expires_after={"anchor": "last_active_at", "days": 7},
)

agent = Agent(
    client=client,
    instructions="Answer only from the indexed documents. Cite the source file.",
    tools=[
        client.get_file_search_tool(
            vector_store_ids=[vector_store.id],
            max_num_results=3,       # 1–50; keep low to control input tokens
        )
    ],
)
```

`get_file_search_tool`: `vector_store_ids` (required, non-empty), `max_num_results`,
`ranking_options`, `filters`. Raises if `vector_store_ids` is empty.

- Always set `expires_after` on demo/dev vector stores. Orphaned stores accumulate cost.
- Provision production vector stores in `infra/`, not in request handling — uploading at
  startup means every replica re-uploads.
- `max_num_results` is your token dial. 3–5 is usually enough and is the difference between a
  fast voice turn and a slow one.

## Azure AI Search — semantic mode (default for voice)

```bash
python -m pip install agent-framework-azure-ai-search --pre
```

```python
from agent_framework.azure import AzureAISearchContextProvider

search = AzureAISearchContextProvider(
    "product_docs",                       # source_id (positional)
    endpoint=os.environ["AZURE_SEARCH_ENDPOINT"],
    index_name=os.environ["AZURE_SEARCH_INDEX_NAME"],
    credential=credential,                # or api_key=... for local dev
    mode="semantic",
    top_k=3,
    semantic_configuration_name="default",
)

async with search:
    agent = Agent(
        client=client,
        instructions="Answer from the provided context. If it is not there, say so.",
        context_providers=[search],
    )
```

**The provider is an async context manager and owns SDK clients.** Use `async with` or call
`await search.close()`. Leaking it leaks connections.

| Parameter | Guidance |
|---|---|
| `top_k` | 3 for voice, 5 default. Every extra doc is input tokens and latency |
| `semantic_configuration_name` | Enables semantic ranking; must exist in your index |
| `vector_field_name` | Optional. If set, `embedding_function` becomes **required** |
| `embedding_function` | Async `str -> list[float]`, or anything satisfying `SupportsGetEmbeddings` |
| `context_prompt` | Prepended to retrieved context |

Set neither `vector_field_name` nor `embedding_function` and the provider inspects the index
schema, auto-discovering vector fields and using integrated vectorization when the index has
a vectorizer. That is the low-friction path — configure the vectorizer on the index.

**Gotcha:** semantic mode joins *every* user and assistant message in the current input into
one query string. In long conversations that query becomes noise. Trim the input, or use
agentic mode, which uses only the last `agentic_message_history_count` messages (default 10).

## Azure AI Search — agentic mode

Supply **exactly one** of `knowledge_base_name` or `index_name`. Both raises.

```python
# Preferred: an existing Knowledge Base
search = AzureAISearchContextProvider(
    endpoint=os.environ["AZURE_SEARCH_ENDPOINT"],
    credential=credential,
    mode="agentic",
    knowledge_base_name=os.environ["AZURE_SEARCH_KNOWLEDGE_BASE_NAME"],
    top_k=3,
)

# Or auto-create a Knowledge Base from an index (needs an Azure OpenAI resource)
search = AzureAISearchContextProvider(
    endpoint=os.environ["AZURE_SEARCH_ENDPOINT"],
    index_name=os.environ["AZURE_SEARCH_INDEX_NAME"],
    credential=credential,
    mode="agentic",
    azure_openai_resource_url=os.environ["AZURE_OPENAI_RESOURCE_URL"],  # required
    model=os.environ["FOUNDRY_MODEL"],                                  # required
)
```

`azure_openai_resource_url` is **not** the Foundry project endpoint — it is the Azure OpenAI
resource URL (`https://<resource>.openai.azure.com`). Getting this wrong is the most common
agentic-mode failure. The auto-created Knowledge Base is named `<index_name>-kb`.

Core KB retrieval works on stable `azure-search-documents` (api-version `2026-04-01`). Two
options need the preview build (`2026-05-01-preview`):

| Option | Stable | Preview |
|---|---|---|
| `knowledge_base_output_mode` | `"extractive_data"` only | `+ "answer_synthesis"` |
| `retrieval_reasoning_effort` | `"minimal"` only | `+ "medium"`, `"low"` |

The provider detects the installed build and raises a clear error. `pip install --pre
azure-search-documents` to enable them — no code change. Do not pin preview in production
without a stated reason.

## Service-side Azure AI Search tool (experimental)

```python
tool = FoundryChatClient.get_azure_ai_search_tool(
    index_connection_id=os.environ["FOUNDRY_SEARCH_CONNECTION_ID"],
    index_name=os.environ["AZURE_SEARCH_INDEX_NAME"],
    query_type="vector_semantic_hybrid",  # simple | semantic | vector | vector_simple_hybrid | vector_semantic_hybrid
    top_k=3,
)
```

Experimental. Requires an Azure AI Search connection on the Foundry project. Gate behind a
flag and note the stage in a comment.

## Large or multi-modal documents — Content Understanding

```bash
python -m pip install agent-framework-azure-contentunderstanding
```

```python
from agent_framework.foundry import ContentUnderstandingContextProvider, FileSearchConfig

cu = ContentUnderstandingContextProvider(
    endpoint=os.environ["AZURE_CONTENTUNDERSTANDING_ENDPOINT"],
    credential=credential,
    # analyzer_id omitted -> auto-selects prebuilt-documentSearch / -audioSearch / -videoSearch
    max_wait=10.0,     # combined budget for CU analysis + vector store upload
    file_search=FileSearchConfig.from_foundry(
        client.client,
        vector_store_id=vector_store.id,
        file_search_tool=file_search_tool,
    ),
)
```

Flow: CU extracts markdown → uploaded to the vector store → the `file_search` tool is
registered on the context → follow-up turns retrieve top-k chunks instead of re-injecting.

`max_wait` is a budget, not a guarantee. Work exceeding it is deferred to the background and
resolves on a later turn — design the UX for "still indexing", especially in voice.
`FileSearchConfig.from_foundry(...)` for `FoundryChatClient`, `.from_openai(...)` for
`OpenAIChatClient`. Implement `FileSearchBackend` for any other vector store service.

## Instructions and citations

Retrieval without instruction discipline produces confident hallucination. Always state:

```text
Answer only from the provided context. If the context does not contain the answer, say you
do not know and offer to escalate. Cite the source document for every factual claim.
```

Citations arrive as annotations on response content. In a voice channel, do not read file IDs
aloud — speak a human-readable source name and expose the link out of band.

## Voice-specific guidance

- Prefer **semantic mode or hosted `file_search`** over agentic mode. Query planning adds a
  model round trip you will hear as dead air.
- Keep `top_k` / `max_num_results` at 3.
- If retrieval is unavoidably slow, expose it as a **tool** rather than a context provider and
  pair it with a VoiceLive interim response (`InterimResponseTrigger.TOOL`).
- Instruct the model to summarize retrieved passages rather than reading them verbatim.
  Indexed prose is written to be read, not heard.

## Security

- **Retrieved documents are untrusted input.** A document containing "ignore previous
  instructions" is a prompt-injection vector. Never let retrieved content carry authority over
  system instructions, and never auto-execute actions derived solely from it.
- **Enforce document-level authorization.** A single shared index means every caller can reach
  every document. Apply a security-trimming `filter` derived from the *authenticated*
  identity — never from anything the user typed or said.
- Prefer Entra ID (`credential=`) over `AZURE_SEARCH_API_KEY`.
- Retrieved passages appear in spans when `ENABLE_SENSITIVE_DATA` is on — keep it off in prod.

## Troubleshooting

| Symptom | Cause |
|---|---|
| Provider returns nothing, no error | No user/assistant message with non-empty text in the input |
| `ValueError: embedding_function is required` | `vector_field_name` set without `embedding_function` |
| `SettingNotFoundError` naming both index and KB | Agentic mode given both `index_name` and `knowledge_base_name` |
| `model is required for agentic mode` | Creating a KB from an index without `model` |
| Agentic mode fails resolving the model | `azure_openai_resource_url` pointed at the Foundry project endpoint |
| `answer_synthesis` / `medium` rejected | Stable `azure-search-documents`; install the preview build |
| Answers ignore the corpus | Model chose not to call `file_search` — switch to a context provider or strengthen instructions |
| Latency grows with conversation length | Semantic mode concatenating all input messages into the query |
| Leaked connections on shutdown | Provider not used as `async with` and `close()` never called |
