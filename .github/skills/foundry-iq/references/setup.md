# Setup — Provisioning, RBAC, Env, Verification

Use this to walk a user from "we have documents" to "the agent cites them". Do the steps in
order; every later step fails confusingly if an earlier one was skipped.

## 0. Preflight — five questions to ask before provisioning anything

Ask these first. Each one changes the shape of what you build, and each is expensive to
retrofit.

1. **Where does the content live?** Blob / ADLS Gen2 / an existing index / SharePoint /
   OneLake / SQL / the public web. This picks the knowledge source kind and whether you need
   preview.
2. **Must different callers see different documents?** If yes, you need
   `ingestionPermissionOptions` at ingestion time — it cannot be added later — and you cannot
   use the Foundry Agent Service MCP path for per-caller trimming.
3. **Voice or text?** Voice forces `minimal` reasoning effort and rules out answer synthesis in
   the turn path.
4. **How often does the content change?** Sets `ingestionSchedule`. "Never" is an answer, but
   make it an explicit one.
5. **GA or preview?** Default GA. Preview only for a named capability, behind a flag.

## 1. Region and tier

- The search service must be in a region that supports agentic retrieval. Not all are.
- **Basic tier or higher** if the search service will use a managed identity to reach model
  deployments. Free tier works for portal proof-of-concept only.
- The knowledge base, its knowledge sources, and the index all live on the **same** search
  service. Cross-service composition is not a thing.

## 2. Models

The knowledge base's LLM is **not** the agent's model. It is a separate Azure OpenAI deployment
with its own cost line and its own supported-model list.

| Model family | API version required |
|---|---|
| `gpt-4o`, `gpt-4o-mini`, `gpt-4.1`, `gpt-4.1-mini`, `gpt-4.1-nano`, `gpt-5`, `gpt-5-mini`, `gpt-5-nano` | `2025-11-01-preview` or `2026-05-01-preview` |
| `gpt-5.1`, `gpt-5.2`, `gpt-5.4`, `gpt-5.4-mini`, `gpt-5.4-nano` | `2026-05-01-preview` only |

An LLM is **required** for a `web` knowledge source, **optional** for everything else on
preview, and **unsupported** on `2026-04-01`. Embedding models are separate again and are set
per knowledge source, not per knowledge base.

## 3. RBAC — assign all of these, they are not interchangeable

**On the search service:**

| Role | Assign to | For |
|---|---|---|
| Search Service Contributor | the deploying identity | creating knowledge bases and knowledge sources |
| Search Index Data Contributor | the deploying identity | loading generated indexes during ingestion |
| Search Index Data Reader | the querying identity (your app MI, or the Foundry **project's** MI) | calling `retrieve` and the MCP endpoint |

**On the Foundry / Azure OpenAI resource:**

| Role | Assign to | For |
|---|---|---|
| Cognitive Services User | the **search service's** managed identity | the knowledge base calling its LLM and embedding models |
| Cognitive Services OpenAI User | your app identity | only if you call the Responses API yourself |

**On the Foundry project (agent path only):**

| Role | Assign to | For |
|---|---|---|
| Foundry Project Manager | the deploying user | creating the `RemoteTool` project connection |
| Foundry User | app / caller identities | using the MCP tool from an agent |

Also enable role-based access on the search service and give it a managed identity — both are
opt-in, and both are silent no-ops if you skip them. Note the Foundry roles were renamed from
`Azure AI *`; the IDs did not change, so older Bicep still works.

## 4. Provision in `infra/`

Knowledge sources and knowledge bases are **infrastructure**, not runtime objects. Creating a
knowledge source starts an indexer pipeline; doing that from application code means every
replica restart re-triggers ingestion.

```text
infra/
  search/
    knowledge-sources/    # one definition per source, checked in
    knowledge-base.*      # references sources by name; retrievalInstructions live here
    roles.*               # the RBAC table above
```

Keep `retrievalInstructions`, `answerInstructions`, source `description`s, and
`retrievalReasoningEffort` in that checked-in definition. They are behaviour, they are prompt
surface, and they belong in review — not in a portal click.

## 5. Environment contract

These extend the retrieval block in
[maf-voice-agent/references/env-contract.md](../../maf-voice-agent/references/env-contract.md).
Deployment values only — reasoning effort, instructions, and `top_k` are behaviour and live in
`config/**.yaml`.

| Variable | Notes |
|---|---|
| `AZURE_SEARCH_ENDPOINT` | `https://<service>.search.windows.net` |
| `AZURE_SEARCH_KNOWLEDGE_BASE_NAME` | The knowledge base. Mutually exclusive with `AZURE_SEARCH_INDEX_NAME` in agentic mode |
| `AZURE_SEARCH_API_VERSION` | Pin it. `2026-04-01` or `2026-05-01-preview` |
| `AZURE_SEARCH_MCP_ENDPOINT` | `${AZURE_SEARCH_ENDPOINT}/knowledgebases/<kb>/mcp?api-version=<ver>` |
| `FOUNDRY_KB_CONNECTION_NAME` | Project connection name, agent/MCP path only |
| `AZURE_OPENAI_RESOURCE_URL` | The Azure OpenAI resource URL — **not** the Foundry project endpoint |
| `AZURE_SEARCH_ADMIN_KEY` | Local dev only. Prefer Entra ID |

## 6. Verify, in this order

Each step isolates one failure class. Do not skip ahead — a working portal playground proves
nothing about your GA code path.

1. **Ingestion.** `get_knowledge_source_status(<ks>)` →
   `lastSynchronizationState.status == "success"` and `itemUpdatesProcessed > 0`.
2. **The generated index.** Open it in Search Explorer. Confirm a semantic configuration
   exists and, if there are vector fields, a vectorizer. Run one keyword query.
3. **Raw retrieve, `minimal` effort, `include_activity=True`.** Confirm non-empty
   `references` and read `activity` for per-source counts. If `count` is 0 for a source, the
   problem is indexing, not the agent.
4. **Permissions**, if in scope: call twice — once with the user token, once without — with a
   user who should see less. Different results, or filtering is not on.
5. **Through the agent.** Ask a question whose answer only exists in the corpus. Then ask one
   whose answer does not, and confirm you get "I don't know" rather than a confident guess.
6. **Traces.** Confirm the retrieve span and its token counts reach App Insights — see
   [maf-dev-loop](../../maf-dev-loop/SKILL.md). Log the `activity` array; it is your only
   attribution for retrieval-side token spend.

## 7. Cost and latency, stated up front

Retrieval has its own bill, separate from the agent's model:

| Line item | Driver |
|---|---|
| Ingestion | document count, image verbalization, `contentExtractionMode: standard`, refresh frequency |
| Query planning | `low` / `medium` effort — `modelQueryPlanning` tokens in `activity` |
| Agentic reasoning | `agenticReasoning.reasoningTokens` — this is often the largest number in the array |
| Answer synthesis | `modelAnswerSynthesis` tokens |
| Web summarization | `modelWebSummarization` tokens |
| Search service | tier and replica/partition count |

`minimal` effort removes the first three entirely. Start there and add effort only when you can
show a retrieval-quality problem that planning fixes.

## First-run errors, in the order people hit them

| Error | Fix |
|---|---|
| `DefaultsNotSet` creating a blob source | `contentExtractionMode: standard` needs Content Understanding defaults PATCHed first. Or use `minimal` |
| Model deployment not found from the knowledge base | Search service MI missing **Cognitive Services User** on the Foundry resource |
| `403` calling `retrieve` | Querying identity missing **Search Index Data Reader** |
| `403` from ARM creating the project connection | Missing **Foundry Project Manager** on the Foundry resource |
| `404` on the MCP endpoint | Wrong service URL, wrong knowledge base name, or an unaccepted api-version |
| Knowledge source create rejected | Preview kind or preview parameter on the stable package. `pip install --pre azure-search-documents` |
| Retrieve returns everything for every user | Permission filtering never enabled — check both halves in [knowledge-sources.md](knowledge-sources.md) |
| Works in the portal, fails in code | Portal is always preview. Align your API version or drop the preview-only feature |
