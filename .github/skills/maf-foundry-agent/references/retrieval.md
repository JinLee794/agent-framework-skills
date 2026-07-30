# RAG & Retrieval

Retrieval grounds answers in a **document corpus**. Recalling facts about the *user* is
memory — see [memory-and-context.md](memory-and-context.md). Conflating them produces agents
that "remember" documents and "retrieve" user facts, and both degrade.

## Choose a strategy

| Strategy | Where retrieval runs | Pick when |
|---|---|---|
| **`AzureAISearchContextProvider`, `mode="semantic"`** | your process, before each run | Ground every turn in the configured Azure AI Search index |

Index creation, chunking, embedding, upload, and live checks belong to the `ai-search` skill.
This file covers only how MAF consumes that finished index.

The context provider retrieves before every run. If retrieval should be on demand, wrap a
direct `SearchClient` query in a local `@tool`; it still uses the same Search endpoint and key.

## Azure AI Search — semantic mode (default for voice)

```bash
python -m pip install agent-framework-azure-ai-search --pre
```

```python
from agent_framework.azure import AzureAISearchContextProvider

async with client.project_client.get_openai_client() as embedding_client:
  async def embed_query(text: str) -> list[float]:
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
    filter=security_filter,
  ) as search:
    agent = Agent(
      client=client,
      instructions=cfg.instructions,
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
  instructions" is a prompt-injection vector. Never let retrieved content carry authority over
  system instructions, and never auto-execute actions derived solely from it.
- **Enforce document-level authorization.** A single shared index means every caller can reach
  every document. Apply a security-trimming `filter` derived from the *authenticated*
  identity — never from anything the user typed or said.
- Read `AZURE_SEARCH_API_KEY` from settings and pass it through `api_key=`. Never place it in
  YAML, source code, a request, or a transcript.
- Retrieved passages appear in spans when `ENABLE_SENSITIVE_DATA` is on — keep it off in prod.

## Troubleshooting

| Symptom | Cause |
|---|---|
| Provider returns nothing, no error | No user/assistant message with non-empty text in the input |
| `ValueError: embedding_function is required` | `vector_field_name` set without `embedding_function` |
| Latency grows with conversation length | Semantic mode concatenating all input messages into the query |
| Leaked connections on shutdown | Provider not used as `async with` and `close()` never called |
