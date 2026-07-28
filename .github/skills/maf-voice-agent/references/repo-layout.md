# Repository Layout — Annotated

Expanded form of the canonical layout in `SKILL.md`. Deviate only with a recorded reason.

```text
<repo>/
├── config/                          # BEHAVIOUR CONTRACT — see maf-agent-config skill
│   ├── agents/
│   │   ├── _base.agent.yaml         # fragment; cannot be loaded directly
│   │   ├── concierge.agent.yaml     # instructions, model, tools, providers
│   │   └── triage.agent.yaml
│   ├── voice/
│   │   ├── _base.voice.yaml
│   │   ├── concierge.voice.yaml     # topology, connection, session (-> RequestSession)
│   │   └── telephony.voice.yaml
│   ├── profiles/
│   │   ├── local.yaml               # overlay only, never a complete config
│   │   └── prod.yaml
│   └── schemas/
│       ├── agent.schema.json        # generated; committed; CI fails on drift
│       └── voice.schema.json
├── src/<package>/
│   ├── __init__.py
│   ├── settings.py                 # ONLY place that reads os.environ
│   ├── config/
│   │   ├── models.py               # pydantic v2 config models
│   │   ├── loader.py               # extends merge, ${ENV}, startup validation
│   │   ├── registry.py             # ref string -> callable; no importlib from config
│   │   └── builders.py             # AgentConfig -> Agent ; VoiceConfig -> RequestSession
│   ├── agents/
│   │   ├── __init__.py
│   │   └── concierge.py            # thin overrides only; behaviour lives in YAML
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── booking.py              # @tool functions; pure; no agent imports
│   │   └── knowledge.py
│   ├── voice/
│   │   ├── __init__.py
│   │   ├── audio.py                # capture/playback, barge-in, buffer management
│   │   └── loop.py                 # async for event in connection: dispatch
│   ├── memory/
│   │   ├── __init__.py
│   │   └── providers.py            # FoundryMemoryProvider construction + scoping
│   ├── retrieval/
│   │   ├── __init__.py
│   │   └── providers.py            # AzureAISearchContextProvider / file_search tool factories
│   ├── observability/
│   │   ├── __init__.py
│   │   └── setup.py                # setup_telemetry() -> None ; called once
│   └── hosting/
│       └── server.py               # ResponsesHostServer / InvocationsHostServer entry
├── skills/                          # RUNTIME agent skills (SkillsProvider source)
│   └── refund-policy/
│       ├── SKILL.md
│       ├── references/policy.md
│       └── scripts/validate.py
├── entities/                        # DevUI directory discovery
│   ├── .env                         # shared, gitignored
│   └── concierge/
│       └── __init__.py              # must export: agent = ...
├── infra/
│   ├── main.bicep                   # Foundry project, model deployment, App Insights
│   └── memory-store.bicep           # or a provision_memory_store.py bootstrap script
├── tests/
│   ├── config/                      # every config validates; schemas current
│   ├── tools/                       # unit tests, no network
│   ├── agents/                      # agent tests with a stub chat client
│   └── voice/                       # event-loop tests against recorded event fixtures
├── .github/skills/                  # BUILD-TIME skills (this directory)
├── .env.example
├── pyproject.toml
└── README.md
```

## Why each boundary exists

**`config/` holds behaviour, env holds deployment, `src/` holds code.** These three never
overlap. A prompt in Python cannot be reviewed by a non-engineer; an endpoint in YAML cannot
differ per environment; a secret in either is a leak. When unsure, ask: *would changing this
value change what the agent says or does?* If yes, it is YAML.

**`voice/` no longer builds `RequestSession`.** Session shape comes from
`config/voice/*.voice.yaml` through `config/builders.py`. `voice/` is left with exactly what
it should be: audio buffers, barge-in, reconnect, and event dispatch.

**`settings.py` is the only reader of `os.environ`.** Scattered `os.environ[...]` calls make
it impossible to tell which variables a deployment needs. Expose typed accessors and let
every other module take values as parameters. `load_dotenv()` belongs at the process entry
point, not inside `settings.py`, so tests can control it.

**`tools/` does not import `agents/`.** Tools are the most reusable asset in the repo. Keeping
them agent-free means the same function can be attached to a local `Agent`, declared on a
Foundry agent definition, or exposed through an MCP server without refactoring.

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

Use the **async** credential (`azure.identity.aio`) — the Foundry clients are async, and a
sync credential blocks the event loop on token acquisition.

Launch with `devui ./entities --port 8080`. DevUI loads `entities/.env` for every entity and
`entities/<name>/.env` for one entity; commit `.env.example` only.

Full DevUI conventions — instrumentation flags, entity discovery, and what makes each
component render — are in the [maf-dev-loop skill](../../maf-dev-loop/SKILL.md).

## Test boundaries

| Directory | Network | Fixture strategy |
|---|---|---|
| `tests/config/` | none | validate every file in `config/`; assert schemas are current |
| `tests/tools/` | none | call the function directly |
| `tests/agents/` | none | stub chat client returning canned `ChatResponse` |
| `tests/voice/` | none | replay recorded `ServerEvent` sequences through the dispatcher |
| `tests/integration/` | live | marked, opt-in, requires `az login` |

Audio device access must never be required by the default test run — VoiceLive audio samples
cannot run in headless CI.
