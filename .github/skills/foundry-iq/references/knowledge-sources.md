# Knowledge Sources — Kinds, Ingestion, Re-indexing

A knowledge source is a **top-level, reusable object on the search service**. It is not owned
by a knowledge base; knowledge bases reference it by name. Create the source first.

## Kinds

| Kind | Indexed / remote | Stage | Notes |
|---|---|---|---|
| `searchIndex` | indexed | GA | Wraps an index you already own. **Start here if you have one** |
| `azureBlob` | indexed | GA | Generates a full indexer pipeline from a container (or ADLS Gen2) |
| `oneLake` | indexed | GA | Generates a pipeline from a lakehouse |
| `web` | remote | GA | Live Bing grounding. **Requires an LLM on the knowledge base** |
| `azureSql` | indexed | preview | From a table or view |
| `file` | indexed | preview | Direct upload to Azure AI Search; no external storage, no indexer |
| `indexedSharePoint` | indexed | preview | Pipeline from a SharePoint site; carries ACLs |
| `remoteSharePoint` | remote | preview | Copilot Retrieval API queries SharePoint with the **user's** token |
| `fabricDataAgent`, `fabricOntology` | remote | preview | Token exchanged for a Fabric-scoped token |
| `mcpServer` | remote | preview | Live tool-backed results from an external MCP server |
| `workIQ` | remote | preview | Microsoft 365 organizational signal |

**Indexed** = content is copied into a search index at ingestion time; queried locally with
keyword/vector/hybrid. **Remote** = nothing is ingested; the engine calls the platform's API at
query time. Both flow through the same ranking and rerank pipeline, so results interleave.

Everything below `GA` needs `2026-05-01-preview` and a `--pre` SDK install. Gate it.

## What creating an indexed source actually does

For `azureBlob`, `azureSql`, `oneLake`, `indexedSharePoint`, the service generates four objects
named after the knowledge source and reports them under `createdResources`:

```json
"createdResources": {
  "datasource": "my-blob-ks-datasource",
  "indexer":    "my-blob-ks-indexer",
  "skillset":   "my-blob-ks-skillset",
  "index":      "my-blob-ks-index"
}
```

Rules:

- **Do not edit them.** They follow a fixed template; hand edits break the pipeline.
- **You cannot rename them.** The names derive from the knowledge source name.
- To change chunking, embedding, or extraction, change the **knowledge source definition**.
- Deleting the knowledge source deletes the generated objects — *except* when the source wraps
  an index you brought yourself (`searchIndex`), which is left alone.

## Blob source, annotated

```python
from azure.search.documents.indexes.models import (
    AzureBlobKnowledgeSource, AzureBlobKnowledgeSourceParameters,
    AzureOpenAIVectorizerParameters, KnowledgeBaseAzureOpenAIModel,
    KnowledgeSourceAzureOpenAIVectorizer, KnowledgeSourceIngestionParameters,
)

ks = AzureBlobKnowledgeSource(
    name="hr-policy-ks",
    description="HR policy PDFs. Use for leave, benefits, and conduct questions.",
    azure_blob_parameters=AzureBlobKnowledgeSourceParameters(
        connection_string=blob_connection,      # prefer a managed identity via `identity=`
        container_name="hr-policies",
        folder_path=None,
        is_adls_gen2=False,
        ingestion_parameters=KnowledgeSourceIngestionParameters(
            embedding_model=KnowledgeSourceAzureOpenAIVectorizer(
                azure_open_ai_parameters=AzureOpenAIVectorizerParameters(
                    resource_url=aoai_endpoint,
                    deployment_name="text-embedding-3-large",
                    model_name="text-embedding-3-large",
                )
            ),
            chat_completion_model=KnowledgeBaseAzureOpenAIModel(   # image verbalization
                azure_open_ai_parameters=AzureOpenAIVectorizerParameters(
                    resource_url=aoai_endpoint,
                    deployment_name="gpt-5-mini",
                    model_name="gpt-5-mini",
                )
            ),
            disable_image_verbalization=False,
            content_extraction_mode="minimal",   # or "standard" — see below
            ingestion_schedule=None,
            # ingestion_permission_options=["user_ids", "group_ids"],   # preview; see Permissions
        ),
    ),
)
index_client.create_or_update_knowledge_source(ks)
```

| Parameter | Guidance |
|---|---|
| `description` | Prompt surface at `low`/`medium` effort — this is how the planner decides to query the source. Write it as routing instructions, not marketing |
| `content_extraction_mode` | `minimal` is the cheap default. `standard` invokes Content Understanding and **requires Content Understanding defaults to be set first**, or creation fails with `DefaultsNotSet` |
| `disable_image_verbalization` | Leave `False` when documents carry diagrams or scans; it costs chat-completion tokens per image |
| `ingestion_schedule` | The incremental refresh dial. Unset means one-shot — the index goes stale silently |
| `identity` | Prefer over `connection_string`. Keys in a knowledge source definition are stored, and redacted on read, which makes rotation opaque |

## Re-indexing and refresh

There is no "reindex now" verb. Behaviour depends on how the source was made:

| Source | Refresh mechanism |
|---|---|
| Generated pipeline (`azureBlob`, `azureSql`, `oneLake`, `indexedSharePoint`) | `ingestionSchedule` drives incremental runs. Change the definition (`create_or_update`) to re-run with new settings |
| `searchIndex` (BYO) | You own the indexer. Foundry IQ never writes to it |
| `file` | Re-upload |
| Remote kinds | N/A — always live |

Watch progress with the status endpoint rather than guessing:

```python
status = index_client.get_knowledge_source_status("hr-policy-ks")
# synchronizationStatus, currentSynchronizationState{itemUpdatesProcessed, itemsUpdatesFailed,
# itemsSkipped, errors[{key, docURL, statusCode, componentName, errorMessage}]},
# lastSynchronizationState.status, statistics
```

`itemsSkipped` climbing while `itemUpdatesProcessed` stays flat is the normal signature of an
unsupported content type in the container — check `errors[].componentName`.

## Index requirements when you bring your own

A `searchIndex` knowledge source has real constraints:

- **A semantic configuration is required.** Agentic retrieval implies `semantic` query type;
  there is no search mode to override.
- **Vector fields need a vectorizer definition on the index**, otherwise they are silently
  ignored and you get keyword-only recall with no error.
- **Scoring profiles are not applied** — including `defaultScoringProfile` — and
  `@search.rerankerBoostedScore` is not surfaced. For recency, use freshness-aware retrieval,
  not a scoring profile.
- Query execution uses the knowledge source's `semanticConfigurationName`, `searchFields`, and
  `sourceDataFields`. Renaming a field in the index without updating the source produces a
  `206 Partial Content` at query time, not a startup error.
- **Chunk large documents.** A single document whose grounding content exceeds `maxOutputSize`
  is dropped from the response entirely, with only a warning in the activity array. Long
  manuals and policies must be indexed as chunks with stable ids and source metadata.

## Permissions metadata (preview)

Two halves; both are required or filtering does nothing.

**Ingestion time** — set on the knowledge source, cannot be added later without recreating it:

```python
ingestion_permission_options=["user_ids", "group_ids"]      # or ["sensitivity_label"]
```

| Source | Needs `ingestionPermissionOptions` | Enforced via |
|---|---|---|
| `azureBlob` / ADLS Gen2 | yes | ingested RBAC scopes, ACLs, or Purview labels |
| `oneLake` | yes | ingested Purview sensitivity labels |
| `indexedSharePoint` | yes | ingested SharePoint ACLs or Purview labels |
| `remoteSharePoint` | no | SharePoint evaluates the user's token directly |
| `fabricDataAgent`, `fabricOntology`, `workIQ` | no | token exchanged for a platform-scoped token |

**Query time** — pass the end user's token (scope `https://search.azure.com/.default`) as
`x_ms_query_source_authorization`. See [wiring.md](wiring.md) for where that token comes from
in each topology.

Sensitivity labels, when ingested, come back per reference as `sensitivityLabelInfo` and as an
aggregate `metadata.responseSensitivityLabelInfo` (most restrictive wins). Use the aggregate to
drive a banner or to disable copy/share; do not read label names into a voice response.

If your index is chunked (integrated vectorization or a Text Split skill), the skillset must
project the sensitivity label onto **each chunk row** via index projections. Without it,
chunk-level references are dropped at query time and retrieval quietly degrades.

## Attaching to a knowledge base

```python
KnowledgeSourceReference(name="hr-policy-ks")
```

Per-source behaviour is set either on the reference or per request:

| Setting | Effect |
|---|---|
| `alwaysQuery` / `always_query_source` | Include this source in every query regardless of reasoning effort. Not supported by `mcpServer` sources |
| `fail_on_error` | Make the source required — the whole retrieve returns `502` if it fails, instead of a partial answer |
| `filter_add_on` | OData filter, `searchIndex` sources only. Security trimming lives here |
| `max_output_documents` | Cap this source's contribution before final selection |
| `include_references` / `include_reference_source_data` | Control citation payload size. The latter requires the former |

Use `always_query_source` + `fail_on_error` together for the source that makes an answer
compliant. A partial answer that silently omits the authoritative policy source is worse than
an error.

## Lifecycle

```text
create source  →  attach to a knowledge base  →  query
delete: update or delete every referencing knowledge base FIRST, then delete the source
```

Deleting a source that is still referenced fails and returns the list of blocking knowledge
bases. Deleting an agent or a project connection deletes **neither** the base nor the sources —
those are search-service resources and must be cleaned up separately.
