# GA Conformance Review

Run this before declaring any work complete. Every row is a literal grep target, so this file
is the one place a removed or renamed API may be restated — everywhere else, the owning skill
holds the fact and other skills link to it.

## Removed and renamed APIs

These are the highest-value greps: they compile-and-fail at runtime, often only on a live call.

| Grep for | Verdict | Owner |
|---|---|---|
| `from azure.ai.voicelive import connect` (non-`aio`) | Sync client removed in `1.0.0` — use `azure.ai.voicelive.aio` | `voicelive-realtime` |
| `FoundryAgentTool`, `ResponseFoundryAgentCallItem` | Removed in `1.2.0`; direct Foundry-agent topology is also outside this seed | `voicelive-realtime` |
| `AzureAIClient`, `AzureAIAgentClient`, `AzureAIAgentsProvider`, `AzureAIProjectAgentProvider` | Removed; this seed uses `FoundryChatClient` for project inference | `maf-foundry-agent` |
| `EOUDetection`, `AzureMultilingualSemanticVad`, `OAIVoice`, `ToolChoiceObject`, `Usage` | Renamed | `voicelive-realtime` |
| `threshold=` / `timeout=` on an `AzureSemanticDetection*` object | Use `threshold_level=` / `timeout_ms=`. `threshold=` on the *VAD* itself is still correct | `voicelive-realtime` |
| `"pcm16-16000hz"` (hyphenated) | Audio format enums use underscores — `pcm16_16000hz` | `voicelive-realtime` |
| `AvatarConfig(type=` | Renamed to `avatar_type=` in `1.2.0` | `voicelive-realtime` |

## Behaviour in the wrong home

| Grep for | Verdict |
|---|---|
| `instructions="..."` literal in `src/` | Move to `config/agents/*.agent.yaml` |
| `RequestSession(...)` / `ServerVad(...)` outside the config builders | Move to `config/voice/*.voice.yaml` |
| `os.environ[...]` outside `settings.py` | Route through `settings` |
| Secret or connection string in `config/**.yaml` | Replace with `${VAR}` |
| A full copy of a config per environment | Use `extends` + `profiles/` overlay |
| Agent config or telemetry setup inside `entities/**/__init__.py` | Drift + duplicate exporters |

## Loader and validation

| Grep for | Verdict |
|---|---|
| Pydantic config model without `extra="forbid"` | Typos become silent no-ops |
| `approval:` missing on a `ref` tool in agent YAML | Loader must raise; no default |
| `approval_mode` omitted on a tool with side effects | Add `always_require` |
| `topology: foundry_agent` or `topology: hosted` | Outside this seed's fixed bridge topology; use `maf_bridge` |
| `topology: maf_bridge` without `interim_response` | Dead air during the agent run |
| Committed `*.schema.json` out of sync with the models | Regenerate in CI and diff |

## Lifecycle and authentication

| Grep for | Verdict |
|---|---|
| Missing `load_dotenv()` at the entry point | Agent Framework never loads `.env` |
| Agent constructed at module scope | Breaks DevUI reload; network at import |
| `AzureAISearchContextProvider` not inside `async with` / never `close()`d | Leaks clients |
| `AzureAISearchContextProvider` without `api_key=settings.azure_search_api_key` | Violates the Search API-key contract |
| Knowledge base or search index created per request | Provision once on the existing Search service |
| Resuming a session ID straight from a client request | IDOR — authorize ownership first |
| `FoundryChatClient` without a token credential | Project endpoint authentication fails |
| `OpenAIChatClient`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY` | Resource-level path bypasses the requested Foundry project endpoint |
| Hard-coded connection strings or API keys | Resolve through environment-backed settings |

## Resource boundary

| Grep for | Verdict |
|---|---|
| `AZURE_FOUNDRY_API_KEY` or `AZURE_OPENAI_API_KEY` | Stale alias in this repo; use `FOUNDRY_API_KEY` for the primary resource |
| `AZURE_VOICELIVE_API_KEY` without `AZURE_VOICELIVE_ENDPOINT` | Orphaned override; endpoint and key must be overridden together |
| `${AZURE_VOICELIVE_ENDPOINT}` in committed voice YAML | Makes an optional override mandatory; inherit from Foundry settings |
| `APPLICATIONINSIGHTS_CONNECTION_STRING`, `configure_azure_monitor`, `OTEL_EXPORTER_OTLP_ENDPOINT` | Adds a monitoring resource or collector |
| `FOUNDRY_MEMORY_*`, `FOUNDRY_VECTOR_*`, `AZURE_SEARCH_MCP_*` | Memory, vector-store, or connection path outside the contract |
| Storage, Cosmos DB, Redis, Content Understanding, project connection, managed identity | Third resource or authentication path; reject it |
| Uncommented `AZURE_VOICELIVE_*` in `.env.example` | Optional override accidentally made mandatory |
| Active `.env.example` name outside `FOUNDRY_PROJECT_ENDPOINT`, `FOUNDRY_API_KEY`, `FOUNDRY_MODEL`, `FOUNDRY_EMBEDDING_MODEL`, `AZURE_SEARCH_*` | Environment contract drift |

## Security trimming

| Grep for | Verdict |
|---|---|
| Search index or knowledge base queried without a security filter | Every caller reads every document |
| A Search `filter` built from transcript text or a client-supplied field | Cross-tenant leak — bind from the authenticated session |
| `ENABLE_SENSITIVE_DATA=true` or `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true` in a committed `.env.example` | Ships a privacy default; voice payloads are recordings of real people |
| Committed `entities/**/.env` | Leaks credentials |
| `--host 0.0.0.0` with DevUI auth disabled | Fails closed — and would expose local module execution |
