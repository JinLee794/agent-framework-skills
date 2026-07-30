# Indexing Pipeline - Chunk, Embed, and Push

Keep format extraction at the edge. Once loaders produce `SourceDocument` records, every
format follows the same normalization, chunking, embedding, upload, and deletion path.

## Pipeline shape

```text
load -> normalize -> chunk -> assign stable keys -> embed -> validate -> upload -> delete stale
```

Make each stage a pure function where practical. Keep network operations in an orchestrator so
chunk and key behavior can be tested without Azure.

## 1. Normalize source records

For each `SourceDocument`:

1. Canonicalize `source_uri` before hashing it.
2. Normalize line endings and Unicode consistently.
3. Remove repeated headers, footers, navigation, and extraction artifacts.
4. Preserve semantic separators such as headings, paragraphs, lists, pages, rows, and slides.
5. Reject records whose normalized text is empty.
6. Retain useful locator metadata such as page, slide, sheet, section, or row range.

Do not collapse all whitespace into one line; paragraph boundaries are useful chunk boundaries.
Do not put secrets, access tokens, or raw ACL payloads in searchable content.

## 2. Chunk by model tokens

Use the tokenizer associated with the embedding model when available. For `text-embedding-3`,
`tiktoken`'s `cl100k_base` is a practical local tokenizer. Keep the model maximum separate from
the chosen chunk size.

A good starting point for prose is 600-800 tokens with 80-120 tokens of overlap. This is a
baseline to evaluate, not a universal optimum. Tables, source code, and short FAQ records need
format-aware boundaries.

```python
import tiktoken

encoding = tiktoken.get_encoding("cl100k_base")

def split_tokens(text: str, size: int = 700, overlap: int = 100) -> list[str]:
    if size <= 0 or overlap < 0 or overlap >= size:
        raise ValueError("Require size > overlap >= 0")

    tokens = encoding.encode(text)
    chunks: list[str] = []
    start = 0
    while start < len(tokens):
        chunk = encoding.decode(tokens[start : start + size]).strip()
        if chunk:
            chunks.append(chunk)
        start += size - overlap
    return chunks
```

Prefer a two-pass splitter in production: split first on format boundaries, then split only
oversized sections by tokens. Never send an individual input above the embedding model's token
limit. Also cap total tokens and input count per embedding request.

## 3. Generate stable keys

Azure AI Search keys must be strings. Use a URL-safe digest so source paths and punctuation do
not leak into key syntax.

```python
import base64
import hashlib


def stable_id(value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def chunk_ids(source_uri: str, chunk_index: int) -> tuple[str, str]:
    parent_id = stable_id(source_uri)
    return parent_id, stable_id(f"{parent_id}:{chunk_index}")
```

The chunk index is stable only when loader ordering and chunk settings are deterministic. A
chunking-setting change is a corpus migration: reprocess every source and clean stale keys.
For pipelines that need stable IDs across insertions near the beginning, include a normalized
content digest and explicitly handle duplicate chunks.

## 4. Probe dimensions, then define the schema

Generate one embedding before creating the index. Pass the returned length into the schema
factory.

```python
from azure.search.documents.indexes.models import (
    HnswAlgorithmConfiguration,
    HnswParameters,
    SearchField,
    SearchFieldDataType,
    SearchIndex,
    SearchableField,
    SemanticConfiguration,
    SemanticField,
    SemanticPrioritizedFields,
    SemanticSearch,
    SimpleField,
    VectorSearch,
    VectorSearchAlgorithmMetric,
    VectorSearchProfile,
)


def build_index(name: str, dimensions: int) -> SearchIndex:
    return SearchIndex(
        name=name,
        fields=[
            SimpleField(name="id", type=SearchFieldDataType.String, key=True),
            SimpleField(
                name="parent_id",
                type=SearchFieldDataType.String,
                filterable=True,
            ),
            SearchableField(name="title", type=SearchFieldDataType.String),
            SearchableField(name="content", type=SearchFieldDataType.String),
            SimpleField(
                name="source_uri",
                type=SearchFieldDataType.String,
                filterable=True,
            ),
            SimpleField(
                name="chunk_index",
                type=SearchFieldDataType.Int32,
                filterable=True,
                sortable=True,
            ),
            SearchField(
                name="content_vector",
                type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                searchable=True,
                retrievable=False,
                stored=False,
                vector_search_dimensions=dimensions,
                vector_search_profile_name="content-vector-profile",
            ),
        ],
        vector_search=VectorSearch(
            algorithms=[
                HnswAlgorithmConfiguration(
                    name="content-hnsw",
                    parameters=HnswParameters(
                        metric=VectorSearchAlgorithmMetric.COSINE,
                    ),
                )
            ],
            profiles=[
                VectorSearchProfile(
                    name="content-vector-profile",
                    algorithm_configuration_name="content-hnsw",
                )
            ],
        ),
        semantic_search=SemanticSearch(
            default_configuration_name="content-semantic",
            configurations=[
                SemanticConfiguration(
                    name="content-semantic",
                    prioritized_fields=SemanticPrioritizedFields(
                        title_field=SemanticField(field_name="title"),
                        content_fields=[SemanticField(field_name="content")],
                    ),
                )
            ],
        ),
    )
```

Use `index_client.create_index()` only after a not-found check. Do not call
`create_or_update_index()` blindly against a shared live index: changing a key, field type,
vector dimension, analyzer, or existing vector profile commonly requires a rebuild. Prefer a
versioned name such as `policies-v2`, populate and verify it, then switch the runtime setting.

## 5. Embed bounded batches

```python

def embed_texts(client, deployment: str, texts: list[str]) -> list[list[float]]:
    if not texts or any(not text.strip() for text in texts):
        raise ValueError("Embedding batches must contain non-empty text")

    response = client.embeddings.create(model=deployment, input=texts)
    ordered = sorted(response.data, key=lambda item: item.index)
    if len(ordered) != len(texts):
        raise RuntimeError("Embedding response count does not match input count")
    return [item.embedding for item in ordered]
```

Before each call, count tokens per item and for the whole batch. Current embedding endpoints
also enforce an input-count limit and an aggregate-token limit; leave headroom for quota and
retry smaller on throttling. Use exponential backoff only for retryable statuses such as
`429` and transient `5xx`, not for bad input or deployment errors.

Validate every returned vector:

```python
if any(len(vector) != embedding_dimensions for vector in vectors):
    raise RuntimeError("Embedding dimensions changed during the run")
```

## 6. Build and upload chunk documents

Each payload contains readable source data and exactly one vector:

```python
payload = {
    "id": chunk_id,
    "parent_id": parent_id,
    "title": source.title,
    "content": chunk_text,
    "source_uri": source.source_uri,
    "chunk_index": chunk_index,
    "content_vector": vector,
}
```

Upload in bounded batches and inspect every result:

```python
results = search_client.upload_documents(documents=batch)
failures = [result for result in results if not result.succeeded]
if failures:
    details = "; ".join(
        f"{result.key}: {result.error_message or 'unknown indexing error'}"
        for result in failures
    )
    raise RuntimeError(f"Azure AI Search rejected documents: {details}")
```

A successful HTTP response can contain failed document operations. Do not report success from
the status code alone. Avoid logging payloads because content can contain private data.

## 7. Delete stale chunks safely

`upload_documents()` replaces documents with matching keys, but it cannot infer deleted
chunks. For each changed source:

1. Compute the expected chunk-key set.
2. Query only `id` for the source's `parent_id`.
3. Calculate `live_keys - expected_keys`.
4. Delete exactly that set with `delete_documents(key_name="id", key_values=...)`.
5. Inspect every deletion result.

Do not delete by broad wildcard, index recreation, or a `source_uri` supplied by an untrusted
caller. For a corpus-wide sync, maintain a run manifest and require explicit approval before
deleting sources absent from the new manifest.

Azure AI Search is eventually consistent for query visibility. Retry the post-upload count and
known-answer query for a bounded period rather than assuming immediate visibility.

## 8. Tests that do not need Azure

Unit-test these as pure behavior:

- every emitted chunk is non-empty and within the configured token limit,
- overlap and ordering are deterministic,
- the same source and settings yield the same IDs,
- two distinct source identities do not share a `parent_id`,
- parser output retains title, source locator, and useful metadata,
- embedding responses are rejoined by response index,
- wrong vector dimensions fail before upload,
- partial upload and delete failures fail the run,
- stale-key calculation never removes another parent.

Then use [live-checks.md](live-checks.md) for the small integration test against the `.env`
resource.
