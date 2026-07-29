# Live Checks - Inspect the `.env` Resource

Live checks answer four different questions in order:

1. Did `.env` point to reachable resources?
2. Does the live schema match the embedding deployment and expected fields?
3. Are chunks and vectors actually present?
4. Does retrieval return useful, traceable results for the corpus?

Use the bundled checker after completing [setup.md](setup.md):

```powershell
python .cursor/skills/foundry-iq/scripts/check_search.py
python .cursor/skills/foundry-iq/scripts/check_search.py --query "a corpus-specific question"
```

This workflow never creates, updates, uploads, or deletes. It reports field metadata, index
statistics, and result IDs, titles, and source URIs; it does not print API keys, vectors, or
chunk content.

## 1. Environment and endpoint check

Confirm the script reports the intended:

- Foundry endpoint hostname and embedding deployment,
- Search endpoint hostname, index name, and API version,
- probed embedding dimension.

A working portal session is not evidence that the local process loaded the same values. If a
request fails, inspect the hostname and deployment/index names before rotating keys.

| Failure | Likely class |
|---|---|
| Foundry `401` / `403` | Azure CLI identity is unsigned-in or lacks project data-plane access |
| Foundry `404` | Wrong embedding deployment name or endpoint path |
| Search `401` / `403` | Wrong Search key or insufficient key privilege |
| Search `404` on index | Wrong service or `AZURE_SEARCH_INDEX_NAME` |
| Unsupported API version | SDK/API-version mismatch; align the pinned package and env value |

## 2. Schema check

The minimum expected fields are:

```text
id, parent_id, title, content, source_uri, chunk_index, content_vector
```

Check all of these, not just names:

| Contract | Expected |
|---|---|
| Key | exactly one key field, `id` |
| Readable text | `title` and `content` searchable and retrievable |
| Source metadata | `parent_id` and `source_uri` filterable |
| Vector type | `Collection(Edm.Single)` and searchable |
| Vector dimensions | equal to the live embedding probe |
| Vector profile | present and attached to `content_vector` |
| Semantic config | title maps to `title`; content maps to `content` |

Treat a dimension mismatch as a hard failure. Do not truncate, pad, or reshape vectors. Create
a versioned index with the correct dimensions and re-embed the corpus.

## 3. Statistics and ingestion check

`SearchIndexClient.get_index_statistics()` reports document count, storage size, and vector
index size. Interpret them together:

| State | Meaning |
|---|---|
| `document_count == 0` | No chunks are indexed, regardless of schema correctness |
| documents > 0, vector size == 0 | Vectors may be missing or vector indexing has not become visible yet |
| count higher after unchanged rerun | Keys are unstable or stale chunks were not removed |
| expected count lower than live count | Old source/chunk keys remain |
| expected count higher than live count | Partial indexing failure or skipped source/chunk |

Keep a local ingestion summary with source count, expected chunk count, uploaded count, deleted
count, failed count, embedding deployment, dimension, and chunk-settings version. Do not include
chunk bodies or credentials.

## 4. Query checks

A schema check proves structure; it does not prove usefulness. Use questions chosen from a
small checked-in evaluation set with expected source IDs.

### Keyword

Run a distinctive exact term from the corpus. This confirms readable content is searchable and
returned metadata can support citations.

### Vector

Embed a paraphrase that avoids exact corpus wording and query `content_vector` with
`VectorizedQuery`. A relevant source should appear in the top results.

### Hybrid and semantic

Use the natural-language question as `search_text` and its embedding as a vector query, with
`query_type="semantic"` and the checked-in semantic configuration. Confirm that ranking is
better or at least no worse for the evaluation set; do not assume semantic reranking helps every
corpus.

### Negative

Ask a question known to be outside the corpus. Search always returns nearest neighbors when
asked for `k` results, so retrieval alone does not prove an answer exists. Record score
behavior on positives and negatives and let the runtime grounding policy decline unsupported
answers.

## 5. Security and tenancy check

A Search API key authenticates the application, not an end user. If different callers must see
different chunks, index an authorization field and bind an OData filter from authenticated
session state. Never derive it from transcript text, a query string, or a tool argument.

Test two authenticated sessions that should produce different filters and assert different
result sets. A successful unfiltered query is not a security test.

## 6. Completion gate

Do not wire the agent until all are true:

- endpoint and deployment/index identity match the intended `.env`,
- embedding and vector-field dimensions match,
- live document count equals the ingestion manifest,
- vector storage is nonzero after bounded propagation retries,
- keyword, vector, and hybrid checks return traceable source metadata,
- known-answer evaluation cases retrieve the expected sources,
- negative cases are characterized rather than treated as answers,
- any caller-specific filter is proven with distinct authenticated sessions.
