# Skill Sources — Registry

The single place URLs are maintained. One section per skill in `.github/skills/`.
Fetch order within a section is top to bottom; stop as soon as the question is answered.

Learn MCP endpoint (optional, for `.vscode/mcp.json`): `https://learn.microsoft.com/api/mcp`

## Package pins to check first

Always cheaper than fetching. Probe these before any network call.

| Package | Owns |
|---|---|
| `agent-framework`, `agent-framework-foundry` | agents, clients, providers, middleware, skills |
| `agent-framework-azure-ai-search` | `AzureAISearchContextProvider` |
| `azure-ai-voicelive` | realtime speech-to-speech |
| `azure-ai-projects` | Foundry projects, memory stores, vector stores |
| `azure-search-documents` | index + query APIs, API versions |
| `azure-monitor-opentelemetry` | App Insights exporter |

PyPI release pages carry the authoritative released version and date:
`https://pypi.org/project/<package>/`

## maf-voice-agent (router)

Syncs last — it aggregates facts the other skills establish.

- Agent Framework docs: https://learn.microsoft.com/agent-framework/
- Agent Framework repo: https://github.com/microsoft/agent-framework
- Voice Live overview: https://learn.microsoft.com/azure/ai-services/speech-service/voice-live

## maf-agent-config

Repo convention, not an SDK surface. Sync only the *field names* it maps onto —
`RequestSession` fields via `voicelive-realtime`, agent/tool fields via `maf-foundry-agent`.
No external URLs of its own.

## voicelive-realtime

- Changelog (highest signal): https://github.com/Azure/azure-sdk-for-python/blob/main/sdk/ai/azure-ai-voicelive/CHANGELOG.md
- SDK README + samples: https://github.com/Azure/azure-sdk-for-python/tree/main/sdk/ai/azure-ai-voicelive
- Voice Live how-to: https://learn.microsoft.com/azure/ai-services/speech-service/voice-live-how-to
- API reference: https://learn.microsoft.com/python/api/overview/azure/ai-voicelive-readme

Watch for: API version string, `RequestSession` fields, VAD/EOU class names, audio format enum
spellings, agent-connection kwargs, `VoiceLiveInstrumentor` attributes.

## maf-foundry-agent

Covers the SKILL body plus `references/tools-and-skills.md`, `references/memory-and-context.md`,
and `references/retrieval.md`.

- Foundry docs: https://learn.microsoft.com/azure/ai-foundry/
- Agent Framework docs: https://learn.microsoft.com/agent-framework/
- Python samples: https://github.com/microsoft/agent-framework/tree/main/python/samples
- MCP specification: https://modelcontextprotocol.io/specification
- `azure-ai-projects` changelog: https://github.com/Azure/azure-sdk-for-python/blob/main/sdk/ai/azure-ai-projects/CHANGELOG.md
- Azure AI Search docs: https://learn.microsoft.com/azure/search/
- `azure-search-documents` changelog: https://github.com/Azure/azure-sdk-for-python/blob/main/sdk/search/azure-search-documents/CHANGELOG.md

Watch for: `agent_framework.foundry` exports, hosted tool catalog and stages, session APIs,
hosting servers, `to_prompt_agent`, `@tool` signature and `approval_mode` values, `SKILL.md`
frontmatter spec, `SkillsProvider` API, memory store beta→GA status, scope semantics,
`ContextProvider` hook signatures, stable vs preview search API version, agentic retrieval /
knowledge base surface, vector store lifecycle, citation shape.

## maf-dev-loop

Covers the SKILL body plus `references/observability.md`.

- DevUI docs: https://learn.microsoft.com/agent-framework/devui/
- DevUI package README (highest signal for CLI flags): https://github.com/microsoft/agent-framework/tree/main/python/packages/devui
- DevUI samples: https://github.com/microsoft/agent-framework/tree/main/python/samples/02-agents/devui
- Agent Framework observability: https://learn.microsoft.com/agent-framework/
- Azure Monitor OTel enablement: https://learn.microsoft.com/azure/azure-monitor/app/opentelemetry-enable
- GenAI semantic conventions: https://opentelemetry.io/docs/specs/semconv/gen-ai/

Watch for: CLI flag names (`--instrumentation` vs `--tracing`, auth flags — docs and package
have diverged before), discovery contract (`agent` / `workflow` export), DevUI-specific stream
event names, span/metric attribute names (they still churn), setup function names, the
sensitive-data opt-in flag.

## Link hygiene

If a URL 404s or permanently redirects, fix it here in the same sync pass and note it in the
report. Do not leave a dead link registered, and do not inline a replacement URL in a skill
body.
