# agent-framework-skills

A **template repository** and reusable skill pack for building **Microsoft Agent Framework
(MAF)** agents — with a Foundry-native voice agent (MAF + Azure AI VoiceLive) as the worked
example.

These are [agent skills](https://code.visualstudio.com/docs/copilot/customization/custom-instructions):
progressively-disclosed domain knowledge that a coding agent loads on demand. Generate a repo
from this template, or drop the skills into an existing one, and your agent stops guessing at
API surfaces, config contracts, and GA requirements.

## Use this template

**Generate a new repository** — click **Use this template** on GitHub, or:

```powershell
gh repo create <your-org>/<your-repo> --template JinLee794/agent-framework-skills --private --clone
```

You get `.cursor/skills/` and `.cursor/copilot-instructions.md` ready to go. Add your `src/`,
`config/`, and `tests/` on top — `maf-voice-agent/references/repo-layout.md` describes the
layout the skills assume.

**Or vendor into an existing repo** — the skills are independent and can be adopted one at a
time:

```powershell
git clone https://github.com/JinLee794/agent-framework-skills.git
Copy-Item agent-framework-skills\.cursor\skills\* .cursor\skills\ -Recurse
```

In VS Code, skills under `.cursor/skills/` are discovered automatically.
`.cursor/copilot-instructions.md` is the single routing surface — it maps tasks to skills and
carries the house rules that apply everywhere. Copy it too, or merge its routing table into
your existing instructions file.

### After you generate

1. **Set the routing table.** `.cursor/copilot-instructions.md` lists every skill in the pack.
   Delete rows for skills you removed; add rows for skills you add. No skill restates it.
2. **Rewrite `metadata.author`** in each `SKILL.md` frontmatter — it ships as `MAFVoiceSeed`.
3. **Re-check the house rules.** Rules 1–7 in `copilot-instructions.md` encode opinions about
   declarative config, untrusted callers, and credential handling. Keep the ones that fit your
   project; delete the ones that do not rather than leaving a rule your code violates.
4. **Wire up an MCP server or two** — see [MCP servers that help](#mcp-servers-that-help).
   The Learn MCP is free, needs no auth, and is what the sync procedure prefers.
5. **Run a sync pass.** `metadata.last-reviewed` on every skill reads `2026-07-28`. See
   [Keeping skills truthful](#keeping-skills-truthful).

## What's in the pack

| Skill | Load it when you're… |
|---|---|
| `maf-voice-agent` | Scaffolding, choosing a topology, or reviewing for GA conformance |
| `maf-agent-config` | Changing agent instructions, model, tools, voice, or VAD in YAML |
| `voicelive-realtime` | Working with VoiceLive sessions, turn detection, barge-in, avatars |
| `maf-foundry-agent` | Building the reasoning agent — clients, tools, MCP, memory, retrieval |
| `ai-search` | Grounding an agent in your own content — knowledge bases, Azure AI Search, indexing |
| `maf-dev-loop` | Running in DevUI, wiring telemetry, or refreshing a stale skill |
| `mermaid-diagrams` | Producing any diagram — validate-then-preview workflow (not MAF-specific) |
| `skill-pack-audit` | Reviewing a skill pack for duplication, routing drift, and context cost |

Each skill is a `SKILL.md` (the always-relevant contract) plus a `references/` folder loaded
only when a task actually needs that depth.

```text
.cursor/
├─ copilot-instructions.md          # routing table + house rules (always on)
└─ skills/
   ├─ maf-voice-agent/              # SKILL.md + conformance, env-contract, repo-layout
   ├─ maf-agent-config/             # SKILL.md + agent-yaml, voice-yaml
   ├─ voicelive-realtime/           # SKILL.md + session-config, voices-and-avatars
   ├─ maf-foundry-agent/            # SKILL.md + tools-and-skills, memory-and-context, retrieval
   ├─ ai-search/                   # SKILL.md + knowledge-sources, setup, wiring
   ├─ maf-dev-loop/                 # SKILL.md + observability, skill-sync, sources
   ├─ mermaid-diagrams/             # SKILL.md
   └─ skill-pack-audit/             # SKILL.md
```

## The two rules the pack enforces

1. **Behaviour is declarative.** Instructions, model, tools, voice, and VAD live in
   `config/**.yaml`, never as literals in Python. `maf-agent-config` holds the contract.
2. **The caller is untrusted input.** Bind identity, memory `scope`, and security filters from
   the authenticated session, never from a transcript. `maf-voice-agent` holds the rest of the
   non-negotiable GA rules.

## Keeping skills truthful

A skill's value is entirely in its falsifiable claims — version numbers, symbol names, removed
APIs. When those drift, the skill actively causes bugs.

`maf-dev-loop/references/skill-sync.md` defines the sync procedure and its ground-truth
precedence: the installed package first, then release notes, then Microsoft Learn, then repo
samples. Never resolve a conflict by preference.

`skill-pack-audit` covers the other half — whether a claim sits in the right place, exactly
once. Run it after adding a skill, or when the agent starts loading the wrong one.

## MCP servers that help

Skills tell the agent *what is true*; MCP servers let it *check*. The two are complementary —
a sync pass that can query Learn directly is far cheaper and more accurate than one scraping
doc pages, and an agent that can list your actual Foundry deployments stops inventing model
names.

### Dev-time — servers your **coding agent** uses

| Server | Type | Endpoint / install | Why it helps here |
|---|---|---|---|
| [Microsoft Learn](https://github.com/MicrosoftDocs/mcp) | remote | `https://learn.microsoft.com/api/mcp` | **Start here.** Free, no auth. `microsoft_docs_search`, `microsoft_docs_fetch`, `microsoft_code_sample_search` against official docs. The [skill-sync procedure](.cursor/skills/maf-dev-loop/references/skill-sync.md) prefers it over `fetch_webpage` |
| [Microsoft Foundry](https://learn.microsoft.com/azure/ai-foundry/mcp/get-started) | remote | `https://mcp.ai.azure.com` | Models, knowledge, and evaluation tools against your real project — grounds `maf-foundry-agent` and `ai-search` work in deployments that actually exist |
| [Azure MCP Server](https://learn.microsoft.com/azure/developer/azure-mcp-server/) | local | VS Code extension `ms-azuretools.vscode-azure-mcp-server` | Azure AI Search, RBAC, Monitor, and Key Vault tools — covers knowledge-base setup, the role assignments in `ai-search/references/setup.md`, and App Insights queries from `maf-dev-loop` |
| [GitHub](https://github.com/github/github-mcp-server) | remote | `https://api.cursorcopilot.com/mcp` | Reads `microsoft/agent-framework` samples and SDK changelogs at `main`, which is often ahead of the released package |

VS Code reads `.vscode/mcp.json`. The template does not ship one — add what you need:

```jsonc
{
  "servers": {
    "microsoft-learn": { "type": "http", "url": "https://learn.microsoft.com/api/mcp" },
    "microsoft-foundry": { "type": "http", "url": "https://mcp.ai.azure.com" }
  }
}
```

The full first-party catalog is at [microsoft/mcp](https://github.com/microsoft/mcp).

### Runtime — servers your **agent** calls

Different concern, same protocol. The pack covers this too:

- **From a MAF agent** — `get_mcp_tool()` on `FoundryChatClient`, plus `approval_mode`
  semantics: [maf-foundry-agent/references/tools-and-skills.md](.cursor/skills/maf-foundry-agent/references/tools-and-skills.md)
- **From VoiceLive directly** — the speech loop can call a remote MCP server without a round
  trip through your process; `MCPApprovalType` controls consent:
  [voicelive-realtime](.cursor/skills/voicelive-realtime/SKILL.md)
- **A knowledge base as an MCP server** — `AZURE_SEARCH_MCP_ENDPOINT` exposes
  `knowledge_base_retrieve`: [ai-search/references/wiring.md](.cursor/skills/ai-search/references/wiring.md)

> **Trust boundary.** A remote MCP server is third-party code deciding what your agent sees.
> Never auto-approve tools from a server you do not control, and treat every tool result as
> untrusted data — never as instructions. That is house rule 2 applied to tools.

## Sources & references

Every claim in the pack traces back to one of the artifacts below. Skills state facts; they do
not carry URLs — **`.cursor/skills/maf-dev-loop/references/sources.md` is the maintained
registry**, and the sync procedure reads it. The list here mirrors it for browsing; if the two
ever disagree, `sources.md` wins.

### Package pins — check these before any doc fetch

The installed package is the strongest signal for "does this symbol exist". Release pages at
`https://pypi.org/project/<package>/` carry the authoritative version and date.

| Package | Owns |
|---|---|
| `agent-framework`, `agent-framework-foundry` | agents, clients, providers, middleware, skills |
| `agent-framework-azure-ai-search` | `AzureAISearchContextProvider` |
| `azure-ai-voicelive` | realtime speech-to-speech |
| `azure-ai-projects` | Foundry projects, memory stores, vector stores |
| `azure-search-documents` | index + query APIs, API versions |
| `azure-monitor-opentelemetry` | App Insights exporter |

### Microsoft Agent Framework

- [Agent Framework docs](https://learn.microsoft.com/agent-framework/)
- [`microsoft/agent-framework` repo](https://github.com/microsoft/agent-framework)
- [Python samples](https://github.com/microsoft/agent-framework/tree/main/python/samples)
- [DevUI docs](https://learn.microsoft.com/agent-framework/devui/) ·
  [DevUI package README](https://github.com/microsoft/agent-framework/tree/main/python/packages/devui) ·
  [DevUI samples](https://github.com/microsoft/agent-framework/tree/main/python/samples/02-agents/devui)

### Azure AI VoiceLive

- [Voice Live overview](https://learn.microsoft.com/azure/ai-services/speech-service/voice-live)
- [Voice Live how-to](https://learn.microsoft.com/azure/ai-services/speech-service/voice-live-how-to)
- [`azure-ai-voicelive` changelog](https://github.com/Azure/azure-sdk-for-python/blob/main/sdk/ai/azure-ai-voicelive/CHANGELOG.md)
  — highest signal for API version, `RequestSession` fields, VAD class names
- [SDK README + samples](https://github.com/Azure/azure-sdk-for-python/tree/main/sdk/ai/azure-ai-voicelive)
- [API reference](https://learn.microsoft.com/python/api/overview/azure/ai-voicelive-readme)

### Microsoft Foundry

- [Foundry docs](https://learn.microsoft.com/azure/ai-foundry/)
- [`azure-ai-projects` changelog](https://github.com/Azure/azure-sdk-for-python/blob/main/sdk/ai/azure-ai-projects/CHANGELOG.md)

### Foundry IQ & Azure AI Search

- [What is Foundry IQ](https://learn.microsoft.com/azure/foundry/agents/concepts/what-is-ai-search)
- [Connect a knowledge base to an agent](https://learn.microsoft.com/azure/foundry/agents/how-to/ai-search-connect)
- [Knowledge source overview](https://learn.microsoft.com/azure/search/agentic-knowledge-source-overview) ·
  [blob knowledge source how-to](https://learn.microsoft.com/azure/search/agentic-knowledge-source-how-to-blob)
- [Create a knowledge base](https://learn.microsoft.com/azure/search/agentic-retrieval-how-to-create-knowledge-base) ·
  [retrieve](https://learn.microsoft.com/azure/search/agentic-retrieval-how-to-retrieve)
- [Azure AI Search docs](https://learn.microsoft.com/azure/search/) ·
  [`azure-search-documents` changelog](https://github.com/Azure/azure-sdk-for-python/blob/main/sdk/search/azure-search-documents/CHANGELOG.md)

### Observability

- [Azure Monitor OpenTelemetry enablement](https://learn.microsoft.com/azure/azure-monitor/app/opentelemetry-enable)
- [OpenTelemetry GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/)

### Tooling skills

- [VS Code custom instructions & skills](https://code.visualstudio.com/docs/copilot/customization/custom-instructions)
  — ground truth for `skill-pack-audit`
- [Mermaid Chart VS Code extension](https://marketplace.visualstudio.com/items?itemName=MermaidChart.vscode-mermaid-chart)
  — ground truth for `mermaid-diagrams`

### MCP

- [Model Context Protocol specification](https://modelcontextprotocol.io/specification)
- [Microsoft Learn MCP Server overview](https://learn.microsoft.com/training/support/mcp) ·
  [repo](https://github.com/MicrosoftDocs/mcp)
- [microsoft/mcp](https://github.com/microsoft/mcp) — catalog of first-party servers

## License

MIT — see [LICENSE](LICENSE).
