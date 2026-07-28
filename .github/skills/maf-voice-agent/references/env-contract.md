# Environment Variable Contract

Use the names the SDKs already read. Inventing project-specific aliases breaks the built-in
settings loaders (`load_settings(..., env_prefix="FOUNDRY_")`) and the documented samples.

## What does *not* belong here

Environment carries **deployment values only** — endpoints, resource names, credentials,
profile selection. Behaviour (instructions, model tuning, tool lists, voice, VAD thresholds,
interim phrases) belongs in `config/**.yaml`. If a value would change what the agent says or
does, it is not an environment variable. See
[maf-agent-config](../../maf-agent-config/SKILL.md).

YAML references these names as `${VAR}` placeholders; it never contains their values.

## Application

| Variable | Default | Notes |
|---|---|---|
| `APP_PROFILE` | `local` | Selects the overlay at `config/profiles/<APP_PROFILE>.yaml` |

## Microsoft Agent Framework — Foundry

| Variable | Read by | Notes |
|---|---|---|
| `FOUNDRY_PROJECT_ENDPOINT` | `FoundryChatClient`, `FoundryAgent`, `FoundryMemoryProvider` | `https://<account>.services.ai.azure.com/api/projects/<project>` |
| `FOUNDRY_MODEL` | `FoundryChatClient` | Model deployment name, e.g. `gpt-5.4-mini` |
| `FOUNDRY_AGENT_NAME` | `FoundryAgent` | Service-managed prompt agent or hosted agent |
| `FOUNDRY_AGENT_VERSION` | `FoundryAgent` | Required for prompt agents; omit for hosted agents |
| `FOUNDRY_MODELS_ENDPOINT` | `FoundryEmbeddingClient` | Distinct from the project endpoint |
| `FOUNDRY_EMBEDDING_MODEL` | `FoundryEmbeddingClient`, memory store definition | e.g. `text-embedding-3-small` |

## Agent Framework — observability

| Variable | Default | Notes |
|---|---|---|
| `ENABLE_INSTRUMENTATION` | `false` | Must be `true` for MAF spans/metrics |
| `ENABLE_SENSITIVE_DATA` | `false` | Prompts, responses, tool args/results. Dev/test only |
| `ENABLE_CONSOLE_EXPORTERS` | `false` | Local debugging without a collector |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | — | e.g. `http://localhost:4317` for Aspire Dashboard |
| `OTEL_EXPORTER_OTLP_PROTOCOL` | `grpc` | or `http` |
| `OTEL_SERVICE_NAME` | `agent_framework` | Set per service |
| `OTEL_SERVICE_VERSION` | package version | |
| `OTEL_RESOURCE_ATTRIBUTES` | — | e.g. `deployment.environment=dev` |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | — | Prefer `client.configure_azure_monitor()` which reads it from the Foundry project |
| `VS_CODE_EXTENSION_PORT` | — | AI Toolkit / Foundry VS Code extension integration |

## Azure AI VoiceLive

| Variable | Read by | Notes |
|---|---|---|
| `AZURE_VOICELIVE_ENDPOINT` | `connect()` | WebSocket endpoint |
| `AZURE_VOICELIVE_API_KEY` | `AzureKeyCredential` | Local dev only; prefer Entra ID |
| `AZURE_EXPERIMENTAL_ENABLE_GENAI_TRACING` | `VoiceLiveInstrumentor` | Must be `true` to emit voice spans |
| `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` | `VoiceLiveInstrumentor` | Records message content; treat as sensitive |

For topology A, `connect()` also needs the Foundry agent coordinates. Reuse
`FOUNDRY_AGENT_NAME` / `FOUNDRY_AGENT_VERSION` and add `FOUNDRY_PROJECT_NAME` (the bare
project name, not the endpoint URL — `connect(project_name=...)` expects the name).

## Memory

| Variable | Notes |
|---|---|
| `FOUNDRY_MEMORY_STORE` | Memory store name; provisioned in `infra/`. **This is the name this repo uses.** |

The hosted-agent samples use `MEMORY_STORE_NAME` for the same value. Do not introduce it
here — map it in the sample-porting step instead, so there is exactly one name in this repo.

## Retrieval / RAG

Read by `AzureAISearchContextProvider` under the `AZURE_SEARCH_` prefix, so explicit kwargs
override these. See
[maf-foundry-agent/references/retrieval.md](../../maf-foundry-agent/references/retrieval.md)
for how MAF consumes them, and [foundry-iq](../../foundry-iq/SKILL.md) for provisioning the
knowledge base and its sources.

| Variable | Notes |
|---|---|
| `AZURE_SEARCH_ENDPOINT` | `https://<service>.search.windows.net` |
| `AZURE_SEARCH_INDEX_NAME` | Index to query (semantic mode, or to auto-create a Knowledge Base) |
| `AZURE_SEARCH_KNOWLEDGE_BASE_NAME` | Existing Knowledge Base for agentic mode. Mutually exclusive with `AZURE_SEARCH_INDEX_NAME` |
| `AZURE_SEARCH_API_VERSION` | Pin it. `2026-04-01` (GA) or `2026-05-01-preview` |
| `AZURE_SEARCH_MCP_ENDPOINT` | `${AZURE_SEARCH_ENDPOINT}/knowledgebases/<kb>/mcp?api-version=<ver>`. MCP path only |
| `FOUNDRY_KB_CONNECTION_NAME` | Foundry project connection to the knowledge base. Agent/MCP path only |
| `AZURE_SEARCH_API_KEY` | Local dev only; omit to use `credential=` |
| `AZURE_OPENAI_RESOURCE_URL` | Agentic mode only. The Azure OpenAI resource URL — **not** the Foundry project endpoint |
| `FOUNDRY_VECTOR_STORE_ID` | Pre-provisioned vector store for hosted `file_search` |
| `AZURE_CONTENTUNDERSTANDING_ENDPOINT` | Only when ingesting large or multi-modal documents |

## `.env.example` template

```bash
# --- Application ---
APP_PROFILE=local

# --- Foundry ---
FOUNDRY_PROJECT_ENDPOINT=https://<account>.services.ai.azure.com/api/projects/<project>
FOUNDRY_PROJECT_NAME=<project>
FOUNDRY_MODEL=gpt-5.4-mini
FOUNDRY_EMBEDDING_MODEL=text-embedding-3-small
FOUNDRY_AGENT_NAME=
FOUNDRY_AGENT_VERSION=

# --- VoiceLive ---
AZURE_VOICELIVE_ENDPOINT=wss://<region>.api.cognitive.microsoft.com/voice-live/realtime
# AZURE_VOICELIVE_API_KEY=   # local dev only; prefer az login + DefaultAzureCredential

# --- Memory ---
FOUNDRY_MEMORY_STORE=

# --- Retrieval (optional) ---
AZURE_SEARCH_ENDPOINT=
AZURE_SEARCH_INDEX_NAME=
# AZURE_SEARCH_KNOWLEDGE_BASE_NAME=   # agentic mode; mutually exclusive with INDEX_NAME
# AZURE_SEARCH_API_VERSION=2026-04-01 # pin it; *-preview only for a named capability
# AZURE_SEARCH_MCP_ENDPOINT=          # MCP path only
# FOUNDRY_KB_CONNECTION_NAME=         # MCP path only
# AZURE_SEARCH_API_KEY=              # local dev only
# AZURE_OPENAI_RESOURCE_URL=         # agentic mode only; NOT the Foundry project endpoint
# FOUNDRY_VECTOR_STORE_ID=

# --- Observability ---
ENABLE_INSTRUMENTATION=true
ENABLE_SENSITIVE_DATA=false
AZURE_EXPERIMENTAL_ENABLE_GENAI_TRACING=true
OTEL_SERVICE_NAME=maf-voice-agent
OTEL_RESOURCE_ATTRIBUTES=deployment.environment=dev
# OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
```

## Loading rules

- Call `load_dotenv()` once, at the process entry point — see `maf-foundry-agent` for why.
- DevUI loads `.env` files itself (entity-level then parent-level).
- In production, prefer app configuration / managed identity over `.env` files entirely.
- Never set `ENABLE_SENSITIVE_DATA=true` or `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true`
  in an environment that handles real caller audio or PII.
