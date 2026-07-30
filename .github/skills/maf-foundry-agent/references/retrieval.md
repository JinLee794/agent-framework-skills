# RAG & Retrieval

Retrieval grounds answers in a **document corpus**. Recalling facts about the *user* is
memory — see [memory-and-context.md](memory-and-context.md). Conflating them produces agents
that "remember" documents and "retrieve" user facts, and both degrade.

## Choose a strategy

| Strategy | Where retrieval runs | Pick when |
|---|---|---|
| **`AzureAISearchContextProvider`, `mode="semantic"`** | your process, before each run | Every caller may read every document in the index |
| **Custom `ContextProvider` over `SearchClient`** | your process, before each run | You need a security-trimming `filter` — see below |
| **Direct `SearchClient` query inside a `@tool`** | your process, only when the model asks | Retrieval is optional, slow, or conditional |

Index creation, chunking, embedding, upload, and live checks belong to the `foundry-iq` skill.
This file covers only how MAF consumes that finished index.

**`AzureAISearchContextProvider` accepts no `filter` parameter.** Its constructor takes
`source_id, endpoint, index_name, api_key, credential, mode, top_k,
semantic_configuration_name, vector_field_name, embedding_function, context_prompt` and the
agentic-mode arguments — there is no OData filter hook. If the index is not readable by every
caller, the built-in provider is the wrong choice: subclass `ContextProvider` and issue the
query yourself so you control `filter`. That is what this seed does.

## Azure AI Search — semantic mode (default for voice)

```bash
python -m pip install agent-framework-azure-ai-search --pre
```

```python
from agent_framework.azure import AzureAISearchContextProvider
from openai import AsyncOpenAI


async def embed_query(text: str) -> list[float]:
    async with AsyncOpenAI(
        base_url=settings.foundry_openai_base_url,  # <resource>/openai/v1/
        api_key=settings.foundry_api_key,
    ) as embedding_client:
        response = await embedding_client.embeddings.create(
            model=settings.foundry_embedding_model,
            input=text,
        )
    return response.data[0].embedding


async with AzureAISearchContextProvider(
    "product_docs",
    endpoint=settings.azure_search_endpoint,
    index_name=settings.azure_search_index_name,
    api_key=settings.azure_search_api_key,
    mode="semantic",
    top_k=3,
    semantic_configuration_name="content-semantic",
    vector_field_name="content_vector",
    embedding_function=embed_query,
) as search:
    agent = build_assistant_agent(client, context_providers=[search])
```

The first argument is `source_id`, not the index name. Reuse a single embedding client in real
code — the snippet opens one per call for brevity, and that is a per-turn connection setup you
do not want on a voice path.

**The provider is an async context manager and owns SDK clients.** Use `async with` or call
`await search.close()`. Leaking it leaks connections.

| Parameter | Guidance |
|---|---|
| `source_id` | First positional argument; must be unique across the agent's providers |
| `top_k` | 3 for voice, 5 default. Every extra doc is input tokens and latency |
| `semantic_configuration_name` | Enables semantic ranking; must exist in your index |
| `vector_field_name` | Optional. If set, `embedding_function` becomes **required** |
| `embedding_function` | Async `str -> list[float]` |
| `api_key` | `str` or `AzureKeyCredential`; use `credential=` for Entra instead |
| `context_prompt` | Prepended to retrieved context |

The code-first index stores vectors but has no integrated vectorizer, so provide both
`vector_field_name` and `embedding_function`. The query and ingestion paths must use the same
embedding deployment and vector dimensions.

**Gotcha:** semantic mode joins every user and assistant message in the current input into one
query string. In long conversations that query becomes noise; trim the input passed to the
provider.

## Instructions and citations

Retrieval without instruction discipline produces confident hallucination. Always state:

```text
Answer only from the provided context. If the context does not contain the answer, say you
do not know and offer to escalate. Cite the source document for every factual claim.
```

Use the indexed `title` and `source_uri` as citation metadata. In a voice channel, speak the
human-readable title and expose the URI out of band.

## Voice-specific guidance

- Keep `top_k` at 3.
- If retrieval is unavoidably slow, expose it as a **tool** rather than a context provider and
  pair it with a VoiceLive interim response (`InterimResponseTrigger.TOOL`).
- Instruct the model to summarize retrieved passages rather than reading them verbatim.
  Indexed prose is written to be read, not heard.

## Security

- **Retrieved documents are untrusted input.** A document containing "ignore previous
  instructions" is a prompt-injection vector. Inject retrieved passages as clearly labelled
  data, never as instructions: use `context.extend_messages(...)` rather than
  `context.extend_instructions(...)`, so the corpus cannot acquire system authority. Never
  auto-execute an action derived solely from retrieved text.
- **Enforce document-level authorization.** A single shared index means every caller can reach
  every document. The filter must be derived from the *authenticated* session and passed in at
  construction — never parsed out of anything the user typed or said, and never accepted as a
  tool argument the model can choose.

```python
from agent_framework import AgentSession, ContextProvider, Message, SessionContext
from azure.core.credentials import AzureKeyCredential
from azure.search.documents.aio import SearchClient


class SecurityTrimmedSearch(ContextProvider):
    def __init__(self, *, endpoint: str, index_name: str, api_key: str, security_filter: str):
        super().__init__("product_docs")  # source_id is a required positional argument
        self._filter = security_filter  # bound from the authenticated session, once
        self._client = SearchClient(endpoint, index_name, AzureKeyCredential(api_key))

    async def before_run(
        self, *, agent, session: AgentSession, context: SessionContext, state: dict
    ) -> None:
        query = next(
            (m.text for m in reversed(list(context.input_messages)) if m.role == "user" and m.text),
            None,
        )
        if not query:
            return
        results = await self._client.search(search_text=query, filter=self._filter, top=3)
        passages = [doc["content"] async for doc in results]
        if passages:
            context.extend_messages(self.source_id, [Message(role="user", contents=passages)])

    async def close(self) -> None:
        await self._client.close()
```

- Read `AZURE_SEARCH_API_KEY` from settings and pass it through `api_key=`. Never place it in
  YAML, source code, a request, or a transcript.
- Own the client's lifetime: close the `SearchClient` (an `AsyncExitStack` in the caller is the
  usual shape) or you leak connections on shutdown.
- Retrieved passages appear in spans when `ENABLE_SENSITIVE_DATA` is on — keep it off in prod.

## Troubleshooting

| Symptom | Cause |
|---|---|
| Provider returns nothing, no error | No user/assistant message with non-empty text in the input |
| `TypeError: unexpected keyword argument 'filter'` | `AzureAISearchContextProvider` has no filter hook; use a custom provider |
| `ValueError: embedding_function is required` | `vector_field_name` set without `embedding_function` |
| Latency grows with conversation length | Semantic mode concatenating all input messages into the query |
| Leaked connections on shutdown | Provider not used as `async with` and `close()` never called |
