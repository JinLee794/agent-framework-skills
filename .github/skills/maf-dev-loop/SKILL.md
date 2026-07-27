---
name: maf-dev-loop
description: "Inner development loop: DevUI local run/debug from entities/, OpenTelemetry and App Insights wiring, trace correlation, and keeping .github/skills in sync with the SDKs. Load when running locally, adding telemetry, or refreshing a stale skill."
license: MIT
compatibility: Python 3.10+; agent-framework-devui (--pre); azure-monitor-opentelemetry; azure-ai-voicelive>=1.2.0.
metadata:
  author: MAFVoiceSeed
  version: "1.0.0"
  verified-against: "Learn /agent-framework/devui + observability docs; microsoft/agent-framework python/packages/devui; azure-ai-voicelive telemetry samples, 2026-07"
---

# Dev Loop — DevUI, Telemetry, Skill Sync

| Task | Where |
|---|---|
| Run and debug an agent locally | this file, below |
| Voice trace attributes, metrics, Aspire, full telemetry troubleshooting | [references/observability.md](references/observability.md) |
| Refresh a stale skill against the SDKs | [references/skill-sync.md](references/skill-sync.md) |

---

# DevUI

DevUI is a **sample app**, not a hosting surface. Never deploy it, never point production
traffic at it, never add repo features that only work because DevUI is running.

```powershell
pip install agent-framework-devui --pre
$env:PYTHONPATH="."; devui ./entities --port 8080
```

Directory discovery (`devui ./entities`) is the default. `serve(entities=[agent])` is for
throwaway scripts only — never in `src/<package>/`.

## `entities/` conventions

```text
entities/
  .env                     # shared across all entities; gitignored
  concierge/
    __init__.py            # MUST export a module-level `agent` (or `workflow`)
    .env                   # entity-scoped overrides; gitignored
```

Not optional:

1. **`__init__.py` exports `agent` or `workflow` at module level.** No other name is
   discovered; a factory function alone is invisible.
2. **`entities/` re-exports; it never redefines.** Load the same YAML and call the same
   `build_*()` factory the voice loop and tests use. Instructions, tool lists, or model names
   written here guarantee drift between what you tested and what ships.
3. **`entity_id` is the agent's `name=`, not the directory name.** Keep them equal.
4. **Use the async credential** (`azure.identity.aio`). A sync credential blocks the loop.
5. **Sibling imports need `PYTHONPATH=.`** or DevUI reports an import error.
6. **`.env` loads automatically** — `entities/.env` then `entities/<name>/.env`. Commit only
   `.env.example`.

```python
# entities/concierge/__init__.py
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import AzureCliCredential

from mypkg.config import build_agent, load_agent_config
from mypkg.settings import settings

agent = build_agent(
    load_agent_config("concierge"),
    client=FoundryChatClient(
        project_endpoint=settings.foundry_project_endpoint,
        model=settings.foundry_model,
        credential=AzureCliCredential(),
    ),
    runtime={"user_id": "devui-local"},
)
```

**MCP tools: no `async with`.** A context manager closes the connection before DevUI invokes
the entity. Construct the tool plainly and let lazy init connect on first use.

**Close what you open.** `register_cleanup(agent, credential.close)` for module-scope clients.

## Making components show up

Check this when "DevUI doesn't show X". Each row is a code convention, not a UI setting.

| Want to see | Your code must |
|---|---|
| The entity in the sidebar | export module-level `agent` / `workflow` from `entities/<name>/__init__.py` |
| Tool calls with arguments | register real `@tool` functions with docstrings and typed params |
| An approve/reject prompt | `approval_mode="always_require"` on the tool |
| Images / files / structured data inline | return `DataContent` / `UriContent`, not a stringified blob |
| Spans in the debug panel | launch with the instrumentation flag (below) |

If the repo grows workflows: give every executor a stable `id=`, build edges explicitly, and
call `await ctx.yield_output(...)` — returning a value is not an output. Verify topology
offline with `WorkflowViz(workflow).to_mermaid()` before blaming the UI. Do not hard-code
`checkpoint_storage=` in `entities/`; DevUI injects workflow-session storage and hard-coding
it removes the checkpoint dropdown.

## Traces in DevUI

DevUI **does not create spans**; it displays the ones Agent Framework already emits.

```powershell
devui ./entities --instrumentation      # newer flag name
devui ./entities --tracing              # name used by the GA docs
```

The flag was renamed and the docs and shipped package have disagreed. Run `devui --help` once
and use what your version lists — do not encode a guess in a task or script.

**The failure that costs the most time:** an `entities/**/__init__.py` that calls
`configure_azure_monitor()` or `configure_otel_providers()` at import. DevUI imports every
entity, so N entities register N provider sets and every span exports N times. Let DevUI's
flag own instrumentation locally.

## Voice agents and DevUI

DevUI has no audio path. It cannot drive a VoiceLive session.

| Topology | Mount in DevUI |
|---|---|
| A — VoiceLive-native Foundry agent | the same config as a local `Agent` entity, to test tools and instructions |
| B — MAF-brain bridge | **the brain agent** — exercise tools, memory, instructions in text before adding audio latency |
| C — hosted `invocations_ws` | the inner agent only |

This works only because of the factory rule: `build_<name>_agent()` returns the same object
whether called by the voice loop, a test, or `entities/`.

## Auth

Auth is on by default; a dev token prints at startup. Unauthenticated mode is permitted **only**
on loopback. Binding `0.0.0.0` or a LAN IP requires `DEVUI_AUTH_TOKEN` / `--auth-token` and
fails closed if combined with the no-auth flag. `--mode user` restricts developer APIs. Never
run DevUI against production credentials — it has hot reload and arbitrary local module import
by design.

---

# Telemetry

## The one-liner you should almost always use

Let the Foundry project supply the Application Insights connection string:

```python
await client.configure_azure_monitor(enable_live_metrics=True)
```

Resolves the connection string from the project's linked App Insights resource, configures
exporters, and enables Agent Framework instrumentation. Requires a linked resource — if none
is linked, link one in `infra/` rather than falling back to a hard-coded string.

| Pattern | Call | When |
|---|---|---|
| Foundry-managed Azure Monitor | `await client.configure_azure_monitor(...)` | **Default** for any Foundry-backed agent |
| Environment variables | `configure_otel_providers()` | Non-Foundry backends; config lives in deployment |
| Explicit exporters | `configure_otel_providers(exporters=[...])` | Custom sampling, multiple destinations |
| Third-party owns providers | `configure_azure_monitor(); enable_instrumentation()` | Another library already set up OTel |
| Zero-code | `opentelemetry-instrument python app.py` | Cannot modify the application |

**Pick exactly one.** More than one initializer registers duplicate providers and
double-exports spans — the usual cause of "why do I see every trace twice".
`ENABLE_INSTRUMENTATION` must be `true` or Agent Framework emits nothing.

## Where to call it

Exactly one `setup_telemetry()` in `src/<package>/observability/setup.py`, invoked from the
process entry point **before any client is constructed**. Instrumentation applied after client
creation misses spans on already-built objects. `entities/` is not an entry point.

```python
async def setup_telemetry(client: FoundryChatClient) -> None:
    if settings.enable_instrumentation:
        await client.configure_azure_monitor(enable_live_metrics=True)
    if settings.enable_voice_tracing:
        os.environ["AZURE_EXPERIMENTAL_ENABLE_GENAI_TRACING"] = "true"
        VoiceLiveInstrumentor().instrument()
```

## Sensitive data

| Flag | Records | Production |
|---|---|---|
| `ENABLE_SENSITIVE_DATA` | prompts, responses, tool args/results | off |
| `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` | VoiceLive message content, transcripts | off |

Voice payloads are recordings and transcripts of real people. Enabling either is a privacy
decision, not a debugging convenience. Never default them to `true` in a committed
`.env.example`; leave `ENABLE_SENSITIVE_DATA` on only in `entities/.env`.

Span/metric names, voice attributes, correlation across topology B, Aspire, and full
troubleshooting: [references/observability.md](references/observability.md).

## Anti-patterns

| Pattern | Verdict |
|---|---|
| Agent instructions, model, or tool list written in `entities/**/__init__.py` | Drift from shipped config — load the YAML, call the factory |
| Telemetry initializer called in an entity module | Duplicate providers across every entity |
| `serve()` called from `src/<package>/` | Move it to `scripts/` |
| More than one `configure_*` initializer | Every span exported twice |
| Telemetry set up after clients are constructed | Misses spans on existing objects |
| `async with` around an MCP tool used by a DevUI entity | Connection closes before first invocation |
| `--host 0.0.0.0` with auth disabled | Fails closed — and would expose local module execution |
| Treating DevUI as the demo or deployment surface | It is a sample app; host with the SDK |
| Committing `entities/**/.env` | Leaks credentials |
| `ENABLE_SENSITIVE_DATA=true` in `.env.example` | Ships a privacy default |
