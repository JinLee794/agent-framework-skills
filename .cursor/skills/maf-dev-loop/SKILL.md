---
name: maf-dev-loop
description: "Inner development loop: text-only DevUI run/debug from entities/, local diagnostics, trace correlation, and skill refresh. Load for DevUI, telemetry, or stale skills. NOT for local microphone/speaker VoiceLive loops - load voicelive-realtime instead."
license: MIT
compatibility: Python 3.10+; agent-framework-devui (--pre).
metadata:
  author: MAFVoiceSeed
   version: "1.2.1"
  last-reviewed: "2026-07-29"
   verified-against: "agent-framework-devui (--pre); Learn /agent-framework/devui + observability docs, 2026-07"
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
4. **Use the same project-backed chat client as the voice loop.** Reuse one async credential.
5. **Sibling imports need `PYTHONPATH=.`** or DevUI reports an import error.
6. **`.env` loads automatically** — `entities/.env` then `entities/<name>/.env`. Commit only
   `.env.example`.

```python
# entities/concierge/__init__.py
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import AzureCliCredential

from mypkg.config import build_agent, load_agent_config
from mypkg.settings import settings

credential = AzureCliCredential()
agent = build_agent(
    load_agent_config("concierge"),
   client=FoundryChatClient(
      project_endpoint=settings.foundry_project_endpoint,
      model=settings.foundry_model,
      credential=credential,
    ),
    runtime={"user_id": "devui-local"},
)
```

Register `credential.close` with the entity cleanup hook so reloads do not leak transports.

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

**The failure that costs the most time:** an `entities/**/__init__.py` that initializes
telemetry at import. DevUI imports every entity, so N entities register N provider sets and
every span exports N times. Let DevUI's flag own instrumentation locally.

## Voice agents and DevUI

DevUI has no audio path. It cannot drive a VoiceLive session.

Mount the **MAF brain agent** in DevUI. Exercise tools, Search retrieval, and instructions in
text before adding VoiceLive latency; DevUI does not drive the audio path.

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

This seed provisions no cloud telemetry resource. Use DevUI's instrumentation flag or console
exporters during local development. Do not add Application Insights, Azure Monitor, or a
deployed OTLP collector to the runtime contract.

Keep local initialization outside `entities/**/__init__.py`; DevUI owns instrumentation when
launched with its tracing flag. Initializing providers in every entity duplicates spans.

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
| Cloud telemetry exporter or collector | Adds a forbidden resource |
| `--host 0.0.0.0` with auth disabled | Fails closed — and would expose local module execution |
| Treating DevUI as the demo or deployment surface | It is a sample app; host with the SDK |
| Committing `entities/**/.env` | Leaks credentials |
| `ENABLE_SENSITIVE_DATA=true` in `.env.example` | Ships a privacy default |
