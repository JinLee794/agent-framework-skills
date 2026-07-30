---
name: maf-dev-loop
description: "Inner development loop: mandatory logging setup, startup preflight, text-only DevUI run/debug from entities/, trace correlation, and diagnosing a silent agent. Load for DevUI, logging, telemetry, or when an agent produces no answer. NOT for local microphone/speaker VoiceLive loops - load voicelive-realtime instead."
license: MIT
compatibility: Python 3.10+; agent-framework 1.12.x (`agent_framework.observability`); agent-framework-devui (--pre).
metadata:
  author: MAFVoiceSeed
  version: "2.0.0"
  last-reviewed: "2026-07-29"
  verified-against: "agent-framework 1.12.1 observability.py introspected in this repo's .venv; agent-framework-devui (--pre); Learn /agent-framework/devui + observability docs, 2026-07"
---

# Dev Loop — Logging, DevUI, Telemetry

| Task | Where |
|---|---|
| Set up logging so failures are explainable | this file, below — **do this first** |
| The agent returns nothing and you cannot tell why | [references/diagnostics.md](references/diagnostics.md) |
| Run and debug an agent locally | this file, below |
| Voice trace attributes, metrics, full telemetry troubleshooting | [references/observability.md](references/observability.md) |
| Refresh a stale skill against the SDKs | [references/skill-sync.md](references/skill-sync.md) |

---

# Logging is not optional

A voice agent fails in places nobody can see: inside a tool handler, inside an event loop,
inside a config document that absorbed a misspelled key. **If the seed cannot explain its own
failure, it is not finished.** Logging setup is scaffolding step one, not a follow-up task.

## `diagnostics.py`

One module, no local imports, called before anything else at every entry point.

```python
# src/<package>/diagnostics.py
import logging
import os

_NOISY = {
    "azure.identity": logging.WARNING,
    "azure.core.pipeline.policies.http_logging_policy": logging.WARNING,
    "urllib3": logging.WARNING,
}


def setup_logging() -> None:
    """Configure root logging. Must run before any module that can fail is imported."""
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-8s %(name)s %(message)s",
        force=True,  # override any handler a dependency installed at import
    )
    for name, noisy_level in _NOISY.items():
        logging.getLogger(name).setLevel(noisy_level)
    logging.getLogger("agent_framework").setLevel(level)
```

`force=True` matters: several Azure SDKs attach a handler on import, and without it
`basicConfig` is a no-op and your format never applies.

```python
# src/<package>/__main__.py — order is load-bearing
from dotenv import load_dotenv

from .diagnostics import setup_logging

load_dotenv()        # Agent Framework never does this for you
setup_logging()      # before any import that can fail

from .voice.runner import main   # noqa: E402 — imported after logging is live
```

Agent Framework's own logger is `agent_framework`, with `agent_framework.declarative` for
document loading. Raising the root level to `DEBUG` gives tool dispatch and HTTP calls.

## Startup preflight

Every entry point runs the same check before opening a session, and a `--check` flag runs it
alone. It must **fail loudly**, never warn and continue.

| Assert | Why |
|---|---|
| Every variable in `.env.example` is set | An unset name becomes an empty string and fails mid-call |
| Every document under `config/` loads and validates | Lazy loading turns a typo into a phone-call failure |
| Each agent document's `model.id` resolved to a literal | Catches `safe_mode` blocking `=Env.` |
| Every declared `function` tool resolved to a callable | `func=None` is silent and calls a no-op |
| The mounted stem in each voice document exists | A mismount looks like a bad prompt |
| A credential can be acquired for the project endpoint | Fails at boot instead of on the first caller |

```powershell
python -m <package> --check
```

Log the four startup facts — loaded documents, resolved model, tool binding status, voice
mounts — at INFO. The exact lines and the triage table that consumes them are in
[references/diagnostics.md](references/diagnostics.md).

## Never swallow an exception

The VoiceLive dispatcher, background `asyncio` tasks, and tool handlers all discard exceptions
by default, which is exactly why "it just goes quiet" is the usual bug report. Log with
`logger.exception(...)`, speak a fallback, and re-raise. Details:
[references/diagnostics.md](references/diagnostics.md).

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

Discovery looks for `agent.py`, `workflow.py`, or `__init__.py` in each directory — **Python
modules only. DevUI never discovers YAML.** This is why `entities/` is directory-per-entity
while `config/` is a flat file per document; do not generalise one shape to the other.

Not optional:

1. **`__init__.py` exports `agent` or `workflow` at module level.** No other name is
   discovered; a factory function alone is invisible.
2. **`entities/` re-exports; it never redefines.** Load the same `config/agents/<name>.yaml`
   through the same `AgentFactory` the voice loop and tests use. Instructions, tool lists, or
   model names written here guarantee drift between what you tested and what ships.
3. **`entity_id` is the agent's `name=`, not the directory name.** Keep them equal.
4. **Use the same credential and bindings as the voice loop.** Reuse one async credential.
5. **Sibling imports need `PYTHONPATH=.`** or DevUI reports an import error.
6. **`.env` loads automatically** — `entities/.env` then `entities/<name>/.env`. Commit only
   `.env.example`.

```python
# entities/concierge/__init__.py
from agent_framework.declarative import AgentFactory
from azure.identity.aio import AzureCliCredential

from mypkg.config import agent_document_path
from mypkg.settings import settings
from mypkg.tools import TOOL_BINDINGS

credential = AzureCliCredential()
agent = AgentFactory(
    client_kwargs={
        "credential": credential,
        "project_endpoint": settings.foundry_project_endpoint,
    },
    bindings=TOOL_BINDINGS,
    safe_mode=False,
).create_agent_from_yaml_path(agent_document_path("concierge"))
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

If the repo grows workflows, their structure and orchestration are owned by
[maf-multi-agent-workflows](../maf-multi-agent-workflows/SKILL.md). Two things are DevUI's
own: verify topology offline with `WorkflowViz(workflow).to_mermaid()` before blaming the UI,
and do not hard-code `checkpoint_storage=` in `entities/` — DevUI injects workflow-session
storage and hard-coding it removes the checkpoint dropdown.

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

Telemetry is a layer on top of logging, not a replacement for it. Get `setup_logging()` and the
preflight working first; spans are useless if the process dies before it emits one.

This seed provisions no cloud telemetry resource. Use DevUI's instrumentation flag or console
exporters during local development. Do not add Application Insights, Azure Monitor, or a
deployed OTLP collector to the runtime contract.

```python
from agent_framework.observability import configure_otel_providers

configure_otel_providers(enable_console_exporters=True)   # or ENABLE_CONSOLE_EXPORTERS=true
```

Instrumentation is **enabled by default** in agent-framework 1.12.x — `enable_instrumentation()`
exists only to force it on programmatically, and `disable_instrumentation()` is sticky. So "no
spans" almost never means instrumentation is off; it means no provider or exporter was
configured, or setup ran after the clients were built.

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

Span/metric names, voice attributes, correlation across topology B, and full telemetry
troubleshooting: [references/observability.md](references/observability.md). Triaging an agent
that returns nothing: [references/diagnostics.md](references/diagnostics.md).

## Anti-patterns

| Pattern | Verdict |
|---|---|
| No `setup_logging()` at an entry point | Failures are invisible; this is the defect that hides every other defect |
| `logging.basicConfig()` without `force=True` | A dependency already installed a handler; your config is a no-op |
| `print()` for diagnostics in `src/` | Not levelled, not filterable, not correlated |
| `except Exception: pass` anywhere in the voice dispatcher | The call goes silent and nothing is recorded |
| A tool handler that raises without a spoken fallback | Caller hears dead air |
| Startup that warns and continues on unset env | Fails on the first real caller instead of at boot |
| Agent instructions, model, or tool list written in `entities/**/__init__.py` | Drift from shipped config — load the document, call the factory |
| Telemetry initializer called in an entity module | Duplicate providers across every entity |
| `serve()` called from `src/<package>/` | Move it to `scripts/` |
| More than one `configure_otel_providers` call | Every span exported twice |
| Telemetry set up after clients are constructed | Misses spans on existing objects |
| Cloud telemetry exporter or collector | Adds a forbidden resource |
| `--host 0.0.0.0` with auth disabled | Fails closed — and would expose local module execution |
| Treating DevUI as the demo or deployment surface | It is a sample app; host with the SDK |
| Committing `entities/**/.env` | Leaks credentials |
| `ENABLE_SENSITIVE_DATA=true` in `.env.example` | Ships a privacy default |
