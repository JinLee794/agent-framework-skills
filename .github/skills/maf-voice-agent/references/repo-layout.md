# Repository Layout — Annotated

Expanded form of the canonical layout in `SKILL.md`. Deviate only with a recorded reason.

```text
<repo>/
├── config/                          # BEHAVIOUR CONTRACT — see maf-agent-config skill
│   ├── agents/                      # kind: Prompt — stock MAF AgentFactory schema
│   │   ├── concierge.yaml
│   │   └── triage.yaml
│   ├── workflows/                   # kind: Workflow — references agent files by path
│   │   └── support.yaml
│   ├── voice/                       # seed-owned VoiceLive session documents
│   │   └── concierge.yaml           # mounts one agent or workflow; one reviewable runtime
│   ├── profiles/
│   │   ├── local.yaml               # overlay only, never a complete document
│   │   ├── telephony.yaml
│   │   └── prod.yaml
│   └── schemas/
│       └── voice.schema.json        # generated; committed; CI fails on drift
├── src/<package>/
│   ├── __init__.py
│   ├── __main__.py                  # entry point: load_dotenv, setup_logging, preflight, run
│   ├── diagnostics.py               # logging setup + preflight; imports nothing local
│   ├── settings.py                  # ONLY place that reads os.environ
│   ├── config/
│   │   ├── models.py                # pydantic v2 models for the VOICE document only
│   │   ├── loader.py                # overlay merge, ${ENV}, startup validation of every document
│   │   ├── bindings.py              # tool name -> callable; the AgentFactory(bindings=) mapping
│   │   └── builders.py              # AgentFactory -> Agent (+providers) ; voice cfg -> RequestSession
│   ├── agents/
│   │   ├── __init__.py
│   │   └── concierge.py             # thin factory; behaviour lives in the agent document
│   ├── tools/
│   │   ├── __init__.py              # exports TOOL_BINDINGS
│   │   ├── booking.py               # tool functions; pure; no agent imports
│   │   └── knowledge.py
│   ├── voice/
│   │   ├── __init__.py
│   │   ├── audio.py                 # capture/playback, barge-in, buffer management
│   │   └── runner.py                # async for event in connection: dispatch
│   ├── retrieval/
│   │   ├── __init__.py
│   │   └── providers.py             # AzureAISearchContextProvider factories
├── skills/                          # RUNTIME agent skills (SkillsProvider source)
│   └── refund-policy/
│       ├── SKILL.md
│       ├── references/policy.md
│       └── scripts/validate.py
├── entities/                        # DevUI directory discovery — Python modules, never YAML
│   ├── .env                         # shared, gitignored
│   └── concierge/
│       └── __init__.py              # must export: agent = ...
├── tests/
│   ├── config/                      # every document loads; schema current; tools all bound
│   ├── tools/                       # unit tests, no network
│   ├── agents/                      # agent tests with a stub chat client
│   └── voice/                       # event-loop tests against recorded event fixtures
├── .github/skills/                  # BUILD-TIME skills (this directory)
├── .env.example
├── pyproject.toml
└── README.md
```

## Why each boundary exists

**Behaviour documents use MAF's schema, not ours.** `config/agents/*.yaml` is `kind: Prompt`,
loaded by the shipped `AgentFactory`; `config/workflows/*.yaml` is `kind: Workflow`, loaded by
`WorkflowFactory`. A private pydantic dialect describing instructions, model, and tools is a
reimplementation of code Microsoft already ships and maintains, and it cannot be read by
DevUI, .NET, or any upstream sample. Only `config/voice/*.yaml` is seed-owned.

**`config/` holds behaviour, env holds deployment, `src/` holds code.** These three never
overlap. A prompt in Python cannot be reviewed by a non-engineer; an endpoint in YAML cannot
differ per environment; a secret in either is a leak. When unsure, ask: *would changing this
value change what the agent says or does?* If yes, it is YAML.

**`diagnostics.py` has no local imports.** Logging must be configured before the first module
that can fail is imported. If it depends on `settings` or `config`, a bad `.env` produces a
silent traceback instead of a logged one.

**`bindings.py` is the only bridge from a YAML tool name to a Python callable.** The
declarative loader builds an unbound tool with `func=None` when a binding is missing, and
nothing raises — the model calls a tool that does nothing. Assert the mapping is total at
startup.

**`voice/` no longer builds `RequestSession`.** Session shape comes from
`config/voice/<name>.yaml` through `config/builders.py`. `voice/` is left with exactly what it
should be: audio buffers, barge-in, reconnect, and event dispatch.

**`settings.py` is the only reader of `os.environ`.** Scattered `os.environ[...]` calls make
it impossible to tell which variables a deployment needs. Expose typed accessors and let
every other module take values as parameters. `load_dotenv()` belongs at the process entry
point, not inside `settings.py`, so tests can control it.

**`tools/` does not import `agents/`.** Tools are the most reusable asset in the repo. Keeping
them agent-free means the same function can be attached to the local `Agent`, tested directly,
or composed into another local agent without refactoring.

**`voice/` contains no business logic.** The VoiceLive event loop is protocol plumbing:
session configuration, audio buffers, barge-in, and event dispatch. If a code reviewer finds
a domain decision in `voice/`, it belongs in a tool or the agent's instructions.

**Agent factories, not module-level agents.** A module-level `agent = Agent(...)` constructs a
client at import time, which breaks tests and DevUI reload. Load config and build; let
`entities/` and the voice loop call the same builder.

**`entities/` re-exports, never redefines.** DevUI requires `__init__.py` to export a variable
named `agent` (or `workflow`). That file loads the same YAML the voice loop loads.
Duplicating instructions or tool lists there guarantees drift.

## `entities/<name>/__init__.py` template

```python
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

Register `credential.close` with the entity cleanup hook.

DevUI discovers `agent.py`, `workflow.py`, or `__init__.py` inside each entity directory —
**Python modules only**. It never discovers YAML, which is why `entities/` is not a place to
put config and why the config tree does not copy its directory-per-entity shape.

Launch with `devui ./entities --port 8080`. DevUI loads `entities/.env` for every entity and
`entities/<name>/.env` for one entity; commit `.env.example` only.

Full DevUI conventions — instrumentation flags, entity discovery, and what makes each
component render — are in the [maf-dev-loop skill](../../maf-dev-loop/SKILL.md).

## Test boundaries

| Directory | Network | Fixture strategy |
|---|---|---|
| `tests/config/` | none | every document in `config/` loads; schema current; every declared tool resolves to a callable |
| `tests/tools/` | none | call the function directly |
| `tests/agents/` | none | stub chat client returning canned `ChatResponse` |
| `tests/voice/` | none | replay recorded `ServerEvent` sequences through the dispatcher |
| `tests/integration/` | live | marked, opt-in, requires `az login` plus Foundry/Search keys |

Audio device access must never be required by the default test run — VoiceLive audio samples
cannot run in headless CI.
