## Repository Skills

This repo is a seed for Foundry-native voice agents built with Microsoft Agent Framework
(MAF) and Azure AI VoiceLive. Skills live in `.github/skills/`. Load the one that matches the
task — you do not need to read them in order, and you should not load more than one or two at
a time. Depth lives in each skill's `references/`; load a reference only when the task
actually needs it.

**This table is the single routing surface for the pack. No skill restates it.**

| Task | Skill |
|---|---|
| Repo layout, topology choice, scaffolding, GA conformance review | `maf-voice-agent` |
| Agent/voice behaviour in YAML — instructions, model, tools, voice, VAD | `maf-agent-config` |
| VoiceLive realtime sessions, VAD, barge-in, voices, avatars | `voicelive-realtime` |
| The reasoning agent — clients, tools, skills, MCP, memory, retrieval, hosting | `maf-foundry-agent` |
| Grounding in your own content — Foundry IQ, knowledge bases, Azure AI Search, indexing | `foundry-iq` |
| Local run/debug in DevUI, telemetry, keeping these skills current | `maf-dev-loop` |
| Provision Foundry resources, deploy models, RBAC, azd, evals | `microsoft-foundry` (user-scoped) |

Tooling skills, unrelated to MAF: `mermaid-diagrams` for any diagram work,
`skill-pack-audit` for reviewing this pack itself.

## House rules

These apply to **all** work in this repo, whether or not you loaded a skill. Each names the
skill that owns the detail — go there rather than re-deriving it.

1. **Behaviour is declarative.** Instructions, model, temperature, tool lists, voice, VAD, and
   interim responses live in `config/**.yaml`; Python loads, validates, and constructs. A
   literal `instructions="..."` or `ServerVad(threshold=...)` in `src/` is a defect.
   → `maf-agent-config`
2. **The caller is untrusted input.** The primary input channel is a human speaking, and a
   caller can claim any identity or attempt prompt injection out loud. Bind identity, memory
   `scope`, and security filters from the *authenticated* session, never from a transcript.
   Retrieved documents are untrusted too — they never change tool selection or filters.
   → `maf-voice-agent`, `foundry-iq`
3. **One `build_<name>_agent(client, **deps) -> Agent` factory per agent.** It is what lets the
   voice loop, DevUI, and tests mount the same object. Never construct an agent at module
   scope. → `maf-foundry-agent`
4. **Agent Framework does not auto-load `.env`.** Call `load_dotenv()` once, at the process
   entry point. → `maf-foundry-agent`
5. **Prefer Foundry-native services over hand-rolled ones.** Memory store over a custom vector
   DB, hosted tools over bespoke HTTP wrappers, toolboxes over per-agent tool duplication, App
   Insights via the project connection over a pasted connection string. → `maf-foundry-agent`
6. **`DefaultAzureCredential`/`AzureCliCredential` locally, a named managed identity in
   production.** Never commit API keys; `AzureKeyCredential` is a local-dev convenience only.
   → `maf-foundry-agent`
7. **Three homes, no overlap.** `config/**.yaml` holds behaviour, env holds deployment values,
   `src/` holds code. A value in the wrong one is the most common defect in this repo.
   → `maf-voice-agent`

Before declaring work complete, run the grep checklist in
`maf-voice-agent/references/conformance.md`.

## Editing these skills

A claim belongs in exactly one skill — the one that owns the SDK surface it describes.
Elsewhere, link to the owner. The only permitted second copy of a falsifiable fact is a row in
the conformance grep table. `skill-pack-audit` explains how to verify this holds.
