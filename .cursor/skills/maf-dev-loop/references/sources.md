# Skill Sources — Registry

The single place URLs are maintained. One section per skill in `.cursor/skills/`.
Fetch order within a section is top to bottom; stop as soon as the question is answered.

Learn MCP endpoint (optional, for `.vscode/mcp.json`): `https://learn.microsoft.com/api/mcp`

## Package pins to check first

Always cheaper than fetching. Probe these before any network call.

| Package | Owns |
|---|---|
| `agent-framework`, `agent-framework-foundry` | agents, project-backed chat client, middleware, skills |
| `azure-identity` | project endpoint token credentials |
| `agent-framework-azure-ai-search` | `AzureAISearchContextProvider` |
| `azure-ai-voicelive` | realtime speech-to-speech |
| `azure-search-documents` | index + query APIs, API versions |
| `openai`, `tiktoken` | project embeddings and token-aware chunking |

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
- Project Responses quickstart: https://learn.microsoft.com/azure/foundry/agents/quickstarts/responses-api
- Agent Framework docs: https://learn.microsoft.com/agent-framework/
- Python samples: https://github.com/microsoft/agent-framework/tree/main/python/samples
- Azure AI Search docs: https://learn.microsoft.com/azure/search/
- `azure-search-documents` changelog: https://github.com/Azure/azure-sdk-for-python/blob/main/sdk/search/azure-search-documents/CHANGELOG.md

Watch for: `FoundryChatClient` project endpoint and token credential fields, session APIs,
`@tool` signature and `approval_mode` values, `SKILL.md` frontmatter, `SkillsProvider` API,
`ContextProvider` hooks, Search API versions, and citation shape.

## foundry-iq

Covers the SKILL body, `references/setup.md`, `references/indexing-pipeline.md`,
`references/live-checks.md`, and `scripts/check_search.py`.

- Vector index overview: https://learn.microsoft.com/azure/search/vector-search-overview
- Create a vector index: https://learn.microsoft.com/azure/search/vector-search-how-to-create-index
- Query a vector index: https://learn.microsoft.com/azure/search/vector-search-how-to-query
- Semantic ranking: https://learn.microsoft.com/azure/search/semantic-search-overview
- Azure OpenAI embeddings: https://learn.microsoft.com/azure/ai-foundry/openai/how-to/embeddings
- `azure-search-documents` changelog: https://github.com/Azure/azure-sdk-for-python/blob/main/sdk/search/azure-search-documents/CHANGELOG.md

Watch for: index field and vector-profile models, semantic configuration fields, upload result
handling, vector query classes, project OpenAI client authentication, embedding request
limits, and embedding dimension behavior.

## maf-dev-loop

Covers the SKILL body plus `references/observability.md`.

- DevUI docs: https://learn.microsoft.com/agent-framework/devui/
- DevUI package README (highest signal for CLI flags): https://github.com/microsoft/agent-framework/tree/main/python/packages/devui
- DevUI samples: https://github.com/microsoft/agent-framework/tree/main/python/samples/02-agents/devui
- Agent Framework observability: https://learn.microsoft.com/agent-framework/
- GenAI semantic conventions: https://opentelemetry.io/docs/specs/semconv/gen-ai/

Watch for: CLI flag names (`--instrumentation` vs `--tracing`, auth flags — docs and package
have diverged before), discovery contract (`agent` / `workflow` export), DevUI-specific stream
event names, span/metric attribute names (they still churn), setup function names, the
sensitive-data opt-in flag.

## Tooling skills

`mermaid-diagrams` and `skill-pack-audit` describe editor and process surfaces, not Azure SDKs,
so they are outside the package-pin sync above. They still go stale — check them on the same
cadence, against different ground truth:

- `mermaid-diagrams` — the Mermaid Chart extension listing:
  https://marketplace.visualstudio.com/items?itemName=MermaidChart.vscode-mermaid-chart
  Watch for: LM tool names, command IDs, slash-command names, and whether the extension has
  resumed writing `.github/instructions/mermaid.instructions.md`.
- `skill-pack-audit` — VS Code custom-instructions and skills docs:
  https://code.visualstudio.com/docs/copilot/customization/custom-instructions
  Watch for: `SKILL.md` frontmatter fields, discovery paths, and how much of a skill the agent
  loads before matching — the invariants depend on that model.

## Link hygiene

If a URL 404s or permanently redirects, fix it here in the same sync pass and note it in the
report. Do not leave a dead link registered, and do not inline a replacement URL in a skill
body.
