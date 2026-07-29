---
name: maf-voice-agent
description: "Repo layout, fixed MAF-bridge topology, two-resource default with optional alternate VoiceLive overrides, and conformance checklist. Load when scaffolding, placing code/config, or reviewing this Foundry + Azure AI Search voice seed before it ships."
license: MIT
compatibility: Python 3.10+; agent-framework + agent-framework-foundry; azure-ai-voicelive (see voicelive-realtime); Microsoft Foundry project endpoint.
metadata:
  author: MAFVoiceSeed
  version: "2.4.0"
  last-reviewed: "2026-07-29"
  verified-against: "Microsoft Agent Framework GA docs and owning repository skills, 2026-07"
---

# Voice Agent — Structure & Topology

The repo-wide house rules are applied by `.cursor/rules/repository.mdc`, which imports the
canonical `.github/copilot-instructions.md`. This skill owns three things no other skill does:
**which topology**, **where files go**, and **the conformance checklist**. Routing to sibling
skills remains in those canonical instructions.

## Fixed integration topology

This seed uses exactly one topology: **B — `maf_bridge`**. A local MAF `Agent` reasons behind
a VoiceLive function tool, and `session.interim_response` is required so retrieval and model
latency do not become dead air.

Use the Foundry project settings for both reasoning and VoiceLive. The settings layer derives
the VoiceLive resource endpoint by removing `/api/projects/<project>` and reuses
`FOUNDRY_API_KEY` / `FOUNDRY_MODEL`. The MAF bridge keeps instructions and tools local:

```python
from agent_framework.foundry import FoundryChatClient
from azure.ai.voicelive.aio import connect
from azure.core.credentials import AzureKeyCredential
from azure.identity.aio import AzureCliCredential

voice_endpoint, voice_key, voice_model = resolve_voicelive_settings()

async with (
  AzureCliCredential() as credential,
  FoundryChatClient(
    project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
    model=os.environ["FOUNDRY_MODEL"],
    credential=credential,
  ) as chat_client,
  connect(
    endpoint=voice_endpoint,
    credential=AzureKeyCredential(voice_key),
    model=voice_model,
  ) as connection,
):
  ...
```

The loader constraints for `maf_bridge` are in `maf-agent-config`.

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
    retrieval/               # RAG: Azure AI Search context providers and tools
    settings.py              # typed env resolution, one place only
  skills/                    # runtime Agent Skills served via SkillsProvider
  entities/                  # DevUI discovery roots; each exports `agent` or `workflow`
  tests/
  .github/skills/            # engineering skills for GitHub Copilot
  .cursor/skills/            # mirrored engineering skills for Cursor (this directory)
  .env.example
```

`config/` holds behaviour, env holds deployment values, `src/` holds code. A value in the
wrong one of those three is the most common config defect.

Two skill roles, deliberately: `skills/` is **runtime** (loaded by `SkillsProvider`);
`.github/skills/` and `.cursor/skills/` are mirrored **build-time** trees loaded by their
respective coding agents. Never ship either build-time tree.

### Layering rules

- `tools/` must not import from `agents/`. Tools are pure, testable, and reusable.
- `voice/` must not contain business logic. It translates audio events to agent invocations.
- `settings.py` exposes only the Foundry and Azure AI Search values in `.env.example`.

## Environment contract

Use the canonical SDK variable names — do not invent new ones. Full table with which component
reads each: [references/env-contract.md](references/env-contract.md).

```bash
FOUNDRY_PROJECT_ENDPOINT=https://<foundry-resource>.services.ai.azure.com/api/projects/<project>
FOUNDRY_API_KEY=<foundry-resource-key>
FOUNDRY_MODEL=gpt-5.4-mini
FOUNDRY_EMBEDDING_MODEL=text-embedding-3-small
AZURE_SEARCH_ENDPOINT=https://<search-service>.search.windows.net
AZURE_SEARCH_API_KEY=<search-key>
AZURE_SEARCH_INDEX_NAME=<index>
AZURE_SEARCH_API_VERSION=2026-04-01

# OPTIONAL: only for VoiceLive on another Foundry resource/project.
# AZURE_VOICELIVE_ENDPOINT=https://<other-foundry-resource>.services.ai.azure.com
# AZURE_VOICELIVE_API_KEY=<other-resource-key>
# AZURE_VOICELIVE_MODEL=<other-model-or-deployment-name>
# AZURE_VOICELIVE_PROFILE=byom-azure-openai-chat-completion
```

## Scaffolding checklist

1. Write `config/agents/<name>.agent.yaml` first, then `config/voice/<name>.voice.yaml` with
  `topology: maf_bridge` and an interim response.
2. Add `settings.py` entries for any new env var and mirror them in `.env.example`. Behaviour
   values go in YAML, never in `.env`.
3. Create each `ref` tool in `tools/` with tests, then register it.
4. Construct project chat with Entra; derive VoiceLive from Foundry settings unless explicitly overridden.
5. Add a DevUI entity that loads the same YAML — no copy-pasted config.
6. Reject dependencies or settings for any Azure resource beyond Foundry and Azure AI Search.
7. Run the conformance review.

## GA-conformance review

The grep checklist is [references/conformance.md](references/conformance.md) — removed APIs,
misplaced behaviour, loader validation, lifecycle, and security trimming. Load it before
declaring any work complete. It is the only file in this pack permitted to restate a fact that
another skill owns, because each row is a literal search pattern.

