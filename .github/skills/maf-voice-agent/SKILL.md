---
name: maf-voice-agent
description: "Non-negotiable GA rules, repo layout, and integration topology for Foundry-native voice agents (MAF + Azure AI VoiceLive). Load when scaffolding, deciding where code goes, choosing a topology, or reviewing for GA conformance."
license: MIT
compatibility: Python 3.10+; azure-ai-voicelive>=1.2.0; agent-framework + agent-framework-foundry; Azure AI Foundry project endpoint.
metadata:
  author: MAFVoiceSeed
  version: "2.0.0"
  verified-against: "azure-ai-voicelive 1.2.0 (GA, api-version 2026-04-10); Microsoft Agent Framework GA docs 2026-07"
---

# Voice Agent — GA Rules & Structure

Four sibling skills cover the rest. Load only the one that matches the task; you do not need
to read this file first unless the task is scaffolding, layout, topology, or a conformance
review.

| Task | Skill |
|---|---|
| Agent/voice behaviour — instructions, model, tools, VAD, voice profile | `maf-agent-config` |
| Realtime speech loop — VAD, barge-in, voices, avatars, audio formats | `voicelive-realtime` |
| The reasoning agent — clients, tools, skills, MCP, memory, retrieval, hosting | `maf-foundry-agent` |
| Local run/debug, telemetry, keeping these skills current | `maf-dev-loop` |
| Provision Foundry resources, deploy models, RBAC, azd, evals | `microsoft-foundry` (user-scoped) |

## Non-negotiable GA rules

This is the single home for these. Apply them before anything else.

1. **Behaviour lives in YAML, not Python.** Instructions, model, temperature, tool lists,
   voice, VAD, and interim responses belong in `config/**.yaml`; Python loads, validates, and
   constructs. A literal `instructions="..."` or `ServerVad(threshold=...)` in `src/` is a
   defect.
2. **The caller is untrusted input.** The primary input channel is a human speaking. A caller
   can claim any identity and can attempt prompt injection out loud. Bind identity, memory
   `scope`, and security filters from the *authenticated* session, never from the transcript.
3. **VoiceLive is async-only.** The sync client was removed in `1.0.0`. Always
   `from azure.ai.voicelive.aio import connect`.
4. **`FoundryAgentTool` no longer exists** (removed in `1.2.0`). To make a Foundry agent the
   voice responder, pass flattened kwargs to `connect(agent_name=..., project_name=...)`.
5. **The `agent_framework.azure` *AI agent clients* were removed** (`AzureAIClient`,
   `AzureAIAgentClient`, `AzureAIAgentsProvider`, `AzureAIProjectAgentProvider`). Use
   `agent_framework.foundry`. The namespace still hosts other surfaces such as
   `AzureAISearchContextProvider` — do not blanket-ban `agent_framework.azure`.
6. **Agent Framework does not auto-load `.env`.** Call `load_dotenv()` at process start.
7. **Prefer Foundry-native services over hand-rolled ones.** Memory store over a custom vector
   DB, hosted tools over bespoke HTTP wrappers, toolboxes over per-agent tool duplication, App
   Insights via the project connection over a pasted connection string.
8. **`DefaultAzureCredential`/`AzureCliCredential` locally, a named managed identity in
   production.** Never commit API keys; `AzureKeyCredential` is a local-dev convenience only.
9. **Output audio format enums use underscores** (`pcm16_16000hz`), not hyphens.
10. **One `build_<name>_agent(client, **deps) -> Agent` factory per agent.** It is what lets
    the voice loop, DevUI, and tests mount the same object without duplication.

## Choose an integration topology

Pick exactly one primary topology per agent and declare it as `topology:` in the voice YAML.
Mixing them is the most common source of duplicated turn-taking and double-billed model calls.

| | A — VoiceLive-native | B — MAF-brain bridge | C — Hosted `invocations_ws` |
|---|---|---|---|
| Who reasons | Foundry agent, service-side | local MAF `Agent` behind a VoiceLive function tool | agent deployed in Foundry |
| Pick when | tools and instructions are stable and can live in the agent definition | you need dynamic tool exposure, per-request instructions, local context providers, or multi-agent | you need Foundry scaling, versioned traffic splitting, server-side session isolation |
| Cost | lowest latency, least code | extra hop; **requires** `interim_response` (`InterimResponseTrigger.TOOL`) or the caller hears silence | deployment complexity |

```python
# A — the responder is the Foundry agent definition
async with connect(
    endpoint=os.environ["AZURE_VOICELIVE_ENDPOINT"],
    credential=DefaultAzureCredential(),
    agent_name=os.environ["FOUNDRY_AGENT_NAME"],
    project_name=os.environ["FOUNDRY_PROJECT_NAME"],
    agent_version=os.getenv("FOUNDRY_AGENT_VERSION"),
) as connection:
    ...
```

A is the default. For C, use the `microsoft-foundry` skill's `invocations-ws` sub-skill for
deployment and this skill set for the agent's internals.

## Canonical repository layout

Full annotations in [references/repo-layout.md](references/repo-layout.md).

```text
<repo>/
  config/                    # THE behaviour contract — agents, voice profiles, overlays, schemas
  src/<package>/
    config/                  # loader: models, extends merge, registry, builders
    agents/                  # thin; builds from AgentConfig — no literal instructions
    tools/                   # @tool functions, grouped by domain; no agent imports
    voice/                   # VoiceLive event loop and audio I/O — no literal session config
    memory/                  # context providers, memory-store provisioning
    retrieval/               # RAG: search context providers, vector store / file_search wiring
    observability/           # single setup_telemetry() entry point
    settings.py              # typed env resolution, one place only
  skills/                    # runtime Agent Skills served via SkillsProvider
  entities/                  # DevUI discovery roots; each exports `agent` or `workflow`
  infra/                     # bicep/azd; Foundry project, models, memory store, index, App Insights
  tests/
  .github/skills/            # engineering skills for the coding agent (this directory)
  .env.example
```

`config/` holds behaviour, env holds deployment values, `src/` holds code. A value in the
wrong one of those three is the most common config defect.

Two skill trees, deliberately: `skills/` is **runtime** (loaded by `SkillsProvider`);
`.github/skills/` is **build-time** (loaded by the coding agent). Never ship the latter.

### Layering rules

- `tools/` must not import from `agents/`. Tools are pure, testable, reusable across A/B/C.
- `voice/` must not contain business logic. It translates audio events to agent invocations.
- Exactly one telemetry initialization call, in `observability/`, from the process entry point
  before any client is constructed.

## Environment contract

Use the canonical SDK variable names — do not invent new ones. Full table with which component
reads each: [references/env-contract.md](references/env-contract.md).

```bash
FOUNDRY_PROJECT_ENDPOINT=https://<account>.services.ai.azure.com/api/projects/<project>
FOUNDRY_MODEL=gpt-5.4-mini
AZURE_VOICELIVE_ENDPOINT=wss://<region>.api.cognitive.microsoft.com/voice-live/realtime
ENABLE_INSTRUMENTATION=true
AZURE_EXPERIMENTAL_ENABLE_GENAI_TRACING=true
```

## Scaffolding checklist

1. Write `config/agents/<name>.agent.yaml` first, then `config/voice/<name>.voice.yaml` with a
   declared `topology:`.
2. Add `settings.py` entries for any new env var and mirror them in `.env.example`. Behaviour
   values go in YAML, never in `.env`.
3. Create each `ref` tool in `tools/` with tests, then register it.
4. Wire telemetry before the first client construction; verify a trace appears.
5. Add a DevUI entity that loads the same YAML — no copy-pasted config.
6. Provision memory stores, vector stores, and search indexes in `infra/`, never at request time.
7. Run the conformance review below.

## GA-conformance review

Grep for these before declaring work complete.

| Pattern | Verdict |
|---|---|
| `instructions="..."` literal in `src/` | Move to `config/agents/*.agent.yaml` |
| `RequestSession(...)` / `ServerVad(...)` outside the config builders | Move to `config/voice/*.voice.yaml` |
| Pydantic config model without `extra="forbid"` | Typos become silent no-ops |
| Secret or connection string in `config/**.yaml` | Replace with `${VAR}` |
| `from azure.ai.voicelive import connect` (non-`aio`) | Removed API |
| `FoundryAgentTool`, `ResponseFoundryAgentCallItem` | Removed in 1.2.0 — use `connect()` kwargs |
| `AzureAIClient`, `AzureAIAgentClient`, `AzureAIAgentsProvider`, `AzureAIProjectAgentProvider` | Removed — use `agent_framework.foundry` |
| `"pcm16-16000hz"` (hyphenated) | Wrong enum value — use `pcm16_16000hz` |
| `EOUDetection`, `AzureMultilingualSemanticVad`, `OAIVoice`, `ToolChoiceObject`, `Usage` | Renamed — see `voicelive-realtime` |
| `threshold=` / `timeout=` on an `AzureSemanticDetection*` object | Use `threshold_level=` / `timeout_ms=`. `threshold=` on the *VAD* is still correct |
| `approval:` missing on a `ref` tool in agent YAML | Loader must raise; no default |
| `approval_mode` omitted on a tool with side effects | Add `always_require` |
| More than one `configure_otel_providers()` / `configure_azure_monitor()` call | Consolidate |
| `AzureAISearchContextProvider` not inside `async with` / never `close()`d | Leaks clients |
| Vector store or memory store created per request | Provision once in `infra/` |
| Search index queried without a security-trimming filter | Every caller reads every document |
| Agent config or telemetry setup inside `entities/**/__init__.py` | Drift + duplicate exporters |
| Hard-coded connection strings or API keys | Replace with credential + env |
