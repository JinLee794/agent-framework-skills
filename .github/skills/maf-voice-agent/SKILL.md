---
name: maf-voice-agent
description: "Repo layout, integration topology, and the environment contract for Foundry-native voice agents (MAF + Azure AI VoiceLive), plus the GA conformance checklist. Load when scaffolding a repo, deciding where code goes, choosing between VoiceLive-native / MAF-bridge / hosted topologies, or reviewing work before it ships."
license: MIT
compatibility: Python 3.10+; azure-ai-voicelive>=1.2.0; agent-framework + agent-framework-foundry; Azure AI Foundry project endpoint.
metadata:
  author: MAFVoiceSeed
  version: "2.1.0"
  last-reviewed: "2026-07-28"
  verified-against: "azure-ai-voicelive 1.2.0 (GA, api-version 2026-04-10); Microsoft Agent Framework GA docs 2026-07"
---

# Voice Agent — Structure & Topology

The repo-wide house rules are in `.github/copilot-instructions.md` and always apply. This skill
owns three things no other skill does: **which topology**, **where files go**, and **the
conformance checklist**. Routing to sibling skills is in `copilot-instructions.md`.

## Choose an integration topology

Pick exactly one primary topology per agent and declare it as `topology:` in the voice YAML.
Mixing them is the most common source of duplicated turn-taking and double-billed model calls.

| | A — VoiceLive-native | B — MAF-brain bridge | C — Hosted `invocations_ws` |
|---|---|---|---|
| `topology:` value in voice YAML | `foundry_agent` | `maf_bridge` | `hosted` |
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
deployment and this skill set for the agent's internals. The loader constraints each topology
enforces are in `maf-agent-config`.

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
6. Provision memory stores, vector stores, knowledge bases, and search indexes in `infra/`,
   never at request time.
7. Run the conformance review.

## GA-conformance review

The grep checklist is [references/conformance.md](references/conformance.md) — removed APIs,
misplaced behaviour, loader validation, lifecycle, and security trimming. Load it before
declaring any work complete. It is the only file in this pack permitted to restate a fact that
another skill owns, because each row is a literal search pattern.

