---
name: ai-search
description: "Build and debug code-first Azure AI Search indexing for Foundry agents: load local files, chunk text, generate embeddings through the Foundry project endpoint, create vector and semantic indexes, upload idempotently, and inspect the live service. Use for RAG ingestion, reindexing, schema mismatches, empty indexes, and retrieval checks. NOT for runtime retrieval wiring - load maf-foundry-agent."
license: MIT
compatibility: "Python 3.10+; openai; azure-identity; azure-search-documents; python-dotenv; tiktoken."
metadata:
  author: MAFVoiceSeed
  version: "2.1.0"
  last-reviewed: "2026-07-29"
  verified-against: "Microsoft Learn - Azure AI Search vector indexes and Azure OpenAI embeddings, 2026-07"
---

# Azure AI Search Indexing for Foundry Agents

Build a repeatable push pipeline that reads content in Python, chunks it in Python, creates
embeddings with the existing Foundry resource, and writes vectors plus readable text directly
to the existing Azure AI Search index.

The resource boundary is deliberate:

```text
local or application-readable files
  -> Python loader and token-aware chunker
  -> Foundry embedding deployment
  -> Azure AI Search push API
```

Do not add Blob Storage, ADLS, Cosmos DB, indexers, skillsets, Content Understanding, project
connections, managed identities, or a second model resource. The local MAF agent consumes the
finished index directly; this workflow ends at a live, verified search index.

Runtime retrieval belongs to
[maf-foundry-agent](../maf-foundry-agent/SKILL.md). Agent and voice behaviour belongs in YAML
and is owned by [maf-agent-config](../maf-agent-config/SKILL.md).

## Load only the depth you need

| Task | Reference |
|---|---|
| Establish packages, `.env`, credentials, and first connection | [references/setup.md](references/setup.md) |
| Implement chunking, stable keys, embeddings, schema, and uploads | [references/indexing-pipeline.md](references/indexing-pipeline.md) |
| Inspect and query the live index without exposing secrets | [references/live-checks.md](references/live-checks.md) |

## Environment contract

Read deployment coordinates from the repository-root `.env`. Never print key values.

| Variable | Purpose |
|---|---|
| `FOUNDRY_PROJECT_ENDPOINT` | Existing project endpoint, ending in `/api/projects/<project>` |
| `FOUNDRY_MODEL` | Chat deployment used by the reasoning and VoiceLive paths |
| `FOUNDRY_EMBEDDING_MODEL` | Embedding deployment name, not the model family guessed from it |
| `AZURE_SEARCH_ENDPOINT` | Existing Azure AI Search service endpoint |
| `AZURE_SEARCH_API_KEY` | Admin key in the indexing process; query key in read-only runtime processes |
| `AZURE_SEARCH_INDEX_NAME` | The exact index to inspect, create, populate, and query |
| `AZURE_SEARCH_API_VERSION` | Pinned Search API version used by the installed SDK |

Do not reuse the chat deployment for embeddings unless it actually is an embedding model.
Call `load_dotenv()` once at the process entry point, before settings are read.

## Procedure

### 1. Inspect before mutating

Load `.env`, construct `SearchIndexClient`, and call `get_index()` plus
`get_index_statistics()` for `AZURE_SEARCH_INDEX_NAME`. Record names, field types, vector
dimensions, vector profile, semantic configuration, document count, and vector index size.

Do not delete or rebuild a live index just because a desired schema differs. Classify the
difference first:

| Live state | Action |
|---|---|
| Index absent | Create it after the embedding probe |
| Schema compatible | Keep it and upload |
| New optional field only | Apply an additive update deliberately |
| Vector dimensions, key, field type, or analyzer differs | Stop; create a versioned index and switch intentionally |
| Existing documents use an unknown key strategy | Stop; determine ownership before writing |

### 2. Probe the embedding deployment

Create one embedding for a short non-empty string and derive the dimension from
`len(response.data[0].embedding)`. The response is the source of truth. Never infer dimensions
from a deployment name.

The vector field's `vector_search_dimensions` must equal that value exactly. The ingestion
and query paths must use the same embedding deployment and dimension setting.

### 3. Define the minimum useful schema

Use one Azure AI Search document per chunk. Keep both readable content and its vector:

| Field | Shape | Why it exists |
|---|---|---|
| `id` | key string | Stable chunk identity and upserts |
| `parent_id` | filterable string | Groups chunks from one source and supports stale-chunk cleanup |
| `title` | searchable string | Result display and semantic title |
| `content` | searchable string | Grounding text, keyword search, and semantic ranking |
| `source_uri` | filterable string | Citation and source traceability |
| `chunk_index` | filterable integer | Deterministic ordering and diagnostics |
| `content_vector` | `Collection(Edm.Single)` | Vector similarity, using the probed dimensions |

Use HNSW with cosine distance for Azure OpenAI embeddings. Add a semantic configuration whose
content field is `content` and whose title field is `title`. Keep `content_vector` out of
normal result payloads.

### 4. Normalize and chunk in code

Give each source a canonical `source_uri`, title, and normalized text. Preserve paragraph and
heading boundaries where possible, then enforce the embedding model's token limit with a
token-aware splitter. Make chunk size and overlap checked-in ingestion settings, not secret
environment values.

Reject empty chunks. Store enough metadata to trace every chunk back to its source. Do not use
character count as a claim about token count.

### 5. Generate deterministic keys

Derive `parent_id` from the canonical source identity and `id` from `parent_id` plus the chunk
ordinal. Use a URL-safe hash. The same corpus and settings must produce the same keys on every
run.

An upsert alone does not remove chunks left behind when a document becomes shorter. Compare
the expected key set with the live key set for each `parent_id`, then delete only stale keys.

### 6. Embed and upload in bounded batches

Batch chunk texts in source order. Preserve the embedding response's item indexes when joining
vectors back to chunks. Enforce all three limits before each request:

- every input is non-empty and below the model's per-input token limit,
- no request contains more than the endpoint's input-count limit,
- aggregate tokens stay below the request limit and deployment quota.

Upload with `SearchClient.upload_documents()`. Treat any returned `IndexingResult` whose
`succeeded` value is false as a failed run; report its key and error message without dumping
document content.

### 7. Verify the live index

After Search reports the upload complete:

1. `get_index_statistics()` reports the expected document count and positive vector storage.
2. An empty or keyword query returns readable `title`, `content`, and `source_uri` fields.
3. A vector query built with the same embedding deployment returns a known relevant chunk.
4. A hybrid plus semantic query returns useful ranking for a corpus-specific question.
5. A negative query does not produce a misleadingly strong known-answer result.

Only after those checks pass should runtime retrieval be wired through `maf-foundry-agent`.

## Completion criteria

- The pipeline runs from a clean environment using only `.env` deployment values and
  checked-in ingestion settings.
- Rerunning unchanged input produces the same keys and document count.
- Removing or shortening a source removes stale chunks from the index.
- Every uploaded vector length matches the live vector field dimension.
- Every upload result is checked, not merely submitted.
- Live keyword, vector, and hybrid checks return readable source metadata.
- No credential value or document body appears in diagnostics.

## Failure signatures

| Symptom | First check |
|---|---|
| Embedding call returns `404` | `FOUNDRY_EMBEDDING_MODEL` is a deployment in `FOUNDRY_PROJECT_ENDPOINT` |
| Upload rejects `content_vector` | Compare the probed vector length with the live field dimensions |
| Upload returns partial success | Inspect every `IndexingResult`; do not rely on the HTTP status alone |
| Document count grows on every run | Chunk keys are random or source identities are not canonical |
| Old passages remain searchable | Stale keys were not deleted for the affected `parent_id` |
| Keyword works but vector search is empty | Vectors are missing, dimensions differ, or the vector profile is not attached |
| Vector results have no usable citations | `source_uri`, `title`, or readable `content` was omitted |
| Portal works but code fails | The code loaded a different `.env`, endpoint, index name, or API version |
