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
| `from agent_framework import SequentialBuilder`, `from agent_framework.workflows import` | Orchestration builders live in `agent_framework.orchestrations` | `maf-multi-agent-workflows` |
| `GroupChat(`, `HandoffOrchestrator(` | Removed in the orchestrations refactor | `maf-multi-agent-workflows` |
| `.with_orchestrator(`, `.with_manager(`, `.with_intermediate_outputs(`, `.register_participants(` | Gone in agent-framework 1.12.1; pass as constructor parameters | `maf-multi-agent-workflows` |
| `register_executor(`, `register_agent(`, `set_start_executor(` | Removed; pass executor/agent instances and `WorkflowBuilder(start_executor=...)` | `maf-multi-agent-workflows` |
| `WorkflowOutputEvent`, `RequestInfoEvent`, `WorkflowStatusEvent`, `ExecutorCompletedEvent` | One `WorkflowEvent`; discriminate on `event.type` | `maf-multi-agent-workflows` |
| `run_stream(`, `run_stream_from_checkpoint(` | `workflow.run(..., stream=True)` / `run(checkpoint_id=...)` | `maf-multi-agent-workflows` |

## Declarative schema conformance

These fail **silently** — no exception, no log line, the capability just never exists. Highest
value rows in the file.

| Grep for | Verdict | Owner |
|---|---|---|
| A pydantic model in `src/` with fields named `instructions`, `temperature`, or `tools` | Reimplements `AgentFactory`; agent documents use `kind: Prompt` | `maf-agent-config` |
| `config/**/*.yaml` under `config/agents/` without `kind: Prompt` | `AgentFactory` raises `DeclarativeLoaderError` | `maf-agent-config` |
| `max_output_tokens`, `top_p`, `output_schema`, `display_name`, `additional_instructions` in an agent document | Schema is camelCase; snake_case keys are absorbed and dropped | `maf-agent-config` |
| `kind: Function`, `kind: MCP`, `kind: OpenAPI` | Tool kinds are lowercase | `maf-agent-config` |
| `type:` inside a tool's `parameters.properties` | Declarative properties use `kind:` | `maf-agent-config` |
| A `kind: function` tool whose `bindings` name is absent from the bindings mapping | Built with `func=None`; the model calls a no-op | `maf-agent-config` |
| `${` inside a `config/agents/**.yaml` document | MAF resolves `=Env.`; `${VAR}` stays a literal | `maf-agent-config` |
| `AgentFactory(` without `safe_mode=False` where the document uses `=Env.` | Default `safe_mode=True` blocks environment access | `maf-agent-config` |
| `AgentFactory(` or `create_agent_from_yaml_path(` on a path built from a request or transcript | Arbitrary environment read via PowerFx | `maf-agent-config` |
| `voice:` or `session:` keys inside `config/agents/**.yaml` | A `kind: Prompt` document cannot carry them | `maf-agent-config` |
| `config/agents/*/agent.yaml` | Flat file per agent; `agent.yaml` is Foundry's deprecated manifest name | `maf-agent-config` |
| `*.yaml` under `src/<package>/` | Config is not code | `maf-voice-agent` |
| `pattern:` inside a workflow document that also has `trigger:` | Ambiguous engine — declarative or builder, not both | `maf-multi-agent-workflows` |
| An `agents:` entry in a workflow document without `file:` or a registered name | Participant never resolves | `maf-multi-agent-workflows` |

## Diagnosability

A seed that cannot explain its own failure is not shippable. Each row is a missing log line or
a swallowed error.

| Grep for | Verdict | Owner |
|---|---|---|
| An entry point without `setup_logging()` before its first local import | Failures are invisible | `maf-dev-loop` |
| `basicConfig(` without `force=True` | A dependency's handler wins; your format never applies | `maf-dev-loop` |
| `print(` in `src/` | Not levelled, filterable, or correlated | `maf-dev-loop` |
| `except Exception:` followed by `pass` or a bare `return` in `voice/` | Call goes silent, nothing recorded | `maf-dev-loop` |
| A tool handler with no `logger.exception` and no spoken fallback | Dead air with no trace | `maf-dev-loop` |
| `asyncio.create_task(` with no done-callback or `await` | Exception surfaces only at interpreter shutdown | `maf-dev-loop` |
| Startup that logs a warning and continues on unset env | Fails on the first real caller instead of at boot | `maf-dev-loop` |
| No startup log of resolved model id, tool binding status, and mounted stem | The four facts every triage needs | `maf-dev-loop` |

## Behaviour in the wrong home

| Grep for | Verdict |
|---|---|
| `instructions="..."` literal in `src/` | Move to `instructions` in `config/agents/<name>.yaml` |
| `RequestSession(...)` / `ServerVad(...)` outside the config builders | Build from `config/voice/<name>.yaml` through the config builder |
| `os.environ[...]` outside `settings.py` | Route through `settings` |
| Secret or connection string in `config/**.yaml` | Replace with a placeholder |
| A full copy of a config per environment | Use a `profiles/` overlay |
| Domain policy repeated in both the agent document and `session.instructions` | Keep policy in the agent document; voice instructions only route and speak |
| Agent config or telemetry setup inside `entities/**/__init__.py` | Drift + duplicate exporters |

## Loader and validation

| Grep for | Verdict |
|---|---|
| Seed pydantic model without `extra="forbid"` | Typos become silent no-ops |
| `approval_mode` omitted on a tool with side effects | Add `always_require` |
| `topology: foundry_agent` or `topology: hosted` | Outside this seed's fixed bridge topology; use `maf_bridge` |
| `topology: maf_bridge` without `interim_response` | Dead air during the agent run |
| `topology: maf_bridge` with `tool_choice: auto` | VoiceLive may skip the MAF bridge; require the bridge tool |
| A voice document whose `mounts` stem has no matching file | Mismount looks like a bad prompt |
| Committed `voice.schema.json` out of sync with the model | Regenerate in CI and diff |
| A generated schema for agent documents | Forks MAF's schema; point editors upstream instead |

## Multi-agent orchestration

| Grep for | Verdict |
|---|---|
| `pattern:` under a workflow document naming a participant with no matching file | Loader must raise |
| A participant document carrying voice keys | Two runtimes claiming one call |
| `pattern: handoff` without `start:` | Loader must raise; no implicit first participant |
| `pattern: group_chat` or `pattern: magentic` without a round or termination limit | Unbounded spend |
| `MagenticBuilder(` without `max_stall_count` / `max_reset_count` | Re-planning loop with no cost ceiling |
| Participants or executors constructed at module scope in `workflows/` | Shared mutable state across callers |
| One `WorkflowBuilder` instance reused across `build()` calls | Same — workflows share executor state |
| `from ..workflows import` inside `agents/` | Import direction is `agents/ ← workflows/`; a participant must mount alone |
| An executor `return`ing a result instead of `await ctx.yield_output(...)` | A return value is not a workflow output |
| `Executor(` subclass without a stable `id=` | Breaks event, trace, and DevUI correlation |
| `connect(` or a VoiceLive session inside `workflows/` | Only one bridge; wrap the workflow with `as_agent()` |
| `CosmosCheckpointStorage`, or any database-backed checkpoint store | Third resource; use in-memory or file locally |
| A retrieval filter that widens for one participant | Privilege escalation by handoff |

## Lifecycle and authentication

| Grep for | Verdict |
|---|---|
| Missing `load_dotenv()` at the entry point | Agent Framework never loads `.env` |
| Agent constructed at module scope | Breaks DevUI reload; network at import |
| `AzureAISearchContextProvider` not inside `async with` / never `close()`d | Leaks clients |
| `AzureAISearchContextProvider` without `api_key=settings.azure_search_api_key` | Violates the Search API-key contract |
| Knowledge base or search index created per request | Provision once on the existing Search service |
| Resuming a session ID straight from a client request | IDOR — authorize ownership first |
| `FoundryChatClient` without a token credential | The project endpoint is Entra-only; it has no `api_key` parameter |
| `FoundryChatClient` where only a resource API key exists | 403 on `agents/write`; use `OpenAIChatClient` on `<resource>/openai/v1/` |
| `OpenAIChatClient` with `azure_endpoint=` and a dated `api_version` | Responses API returns `400 API version not supported`; use `base_url=<resource>/openai/v1/` |
| A separate `AZURE_OPENAI_ENDPOINT` / `AZURE_OPENAI_API_KEY` resource | Third resource outside the two-resource contract |
| Hard-coded connection strings or API keys | Resolve through environment-backed settings |

## Resource boundary

| Grep for | Verdict |
|---|---|
| `AZURE_FOUNDRY_API_KEY` or `AZURE_OPENAI_API_KEY` | Stale alias in this repo; use `FOUNDRY_API_KEY` for the primary resource |
| `AZURE_VOICELIVE_API_KEY` without `AZURE_VOICELIVE_ENDPOINT` | Orphaned override; endpoint and key must be overridden together |
| `${AZURE_VOICELIVE_ENDPOINT}` under committed `voice` config | Makes an optional override mandatory; inherit from Foundry settings |
| `APPLICATIONINSIGHTS_CONNECTION_STRING`, `configure_azure_monitor`, `OTEL_EXPORTER_OTLP_ENDPOINT` | Adds a monitoring resource or collector |
| `FOUNDRY_MEMORY_*`, `FOUNDRY_VECTOR_*`, `AZURE_SEARCH_MCP_*` | Memory, vector-store, or connection path outside the contract |
| Storage, Cosmos DB, Redis, Content Understanding, project connection, managed identity | Third resource or authentication path; reject it |
| Uncommented `AZURE_VOICELIVE_ENDPOINT`, `AZURE_VOICELIVE_API_KEY`, or `AZURE_VOICELIVE_MODEL` in `.env.example` | Optional override accidentally made mandatory. `AZURE_VOICELIVE_PROFILE` is exempt: it selects BYOM vs a Voice Live-managed model |
| Active `.env.example` name outside `FOUNDRY_PROJECT_ENDPOINT`, `FOUNDRY_API_KEY`, `FOUNDRY_MODEL`, `FOUNDRY_EMBEDDING_MODEL`, `AZURE_VOICELIVE_PROFILE`, `AZURE_SEARCH_*` | Environment contract drift |

## Security trimming

| Grep for | Verdict |
|---|---|
| Search index or knowledge base queried without a security filter | Every caller reads every document |
| A Search `filter` built from transcript text or a client-supplied field | Cross-tenant leak — bind from the authenticated session |
| `ENABLE_SENSITIVE_DATA=true` or `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true` in a committed `.env.example` | Ships a privacy default; voice payloads are recordings of real people |
| Committed `entities/**/.env` | Leaks credentials |
| `--host 0.0.0.0` with DevUI auth disabled | Fails closed — and would expose local module execution |
