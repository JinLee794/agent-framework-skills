# agent-framework-skills

A reusable skill pack for building **Microsoft Agent Framework (MAF)** agents — with a
Foundry-native voice agent (MAF + Azure AI VoiceLive) as the worked example.

These are [agent skills](https://code.visualstudio.com/docs/copilot/customization/custom-instructions):
progressively-disclosed domain knowledge that a coding agent loads on demand. Drop them into a
repo and your agent stops guessing at API surfaces, config contracts, and GA requirements.

## What's in the pack

| Skill | Load it when you're… |
|---|---|
| `maf-voice-agent` | Scaffolding, choosing a topology, or reviewing for GA conformance |
| `maf-agent-config` | Changing agent instructions, model, tools, voice, or VAD in YAML |
| `voicelive-realtime` | Working with VoiceLive sessions, turn detection, barge-in, avatars |
| `maf-foundry-agent` | Building the reasoning agent — clients, tools, MCP, memory, retrieval |
| `foundry-iq` | Grounding an agent in your own content — knowledge bases, Azure AI Search, indexing |
| `maf-dev-loop` | Running in DevUI, wiring telemetry, or refreshing a stale skill |
| `mermaid-diagrams` | Producing any diagram — validate-then-preview workflow (not MAF-specific) |
| `skill-pack-audit` | Reviewing a skill pack for duplication, routing drift, and context cost |

Each skill is a `SKILL.md` (the always-relevant contract) plus a `references/` folder loaded
only when a task actually needs that depth. `.github/copilot-instructions.md` is the single
routing surface — it maps tasks to skills and carries the house rules that apply everywhere.

## Install

Copy the skills into the consuming repository:

```powershell
git clone https://github.com/JinLee794/agent-framework-skills.git
Copy-Item agent-framework-skills\.github\skills\* .github\skills\ -Recurse
```

Or vendor a subset — the skills are independent and can be adopted one at a time.

Then point your agent at them. In VS Code, skills under `.github/skills/` are discovered
automatically; `.github/copilot-instructions.md` here shows how to advertise the routing table
so the agent picks the right one.

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

## License

MIT — see [LICENSE](LICENSE).
