## Repository Skills

This repo is a seed for voice agents built with Microsoft Agent Framework (MAF), one Microsoft
Foundry resource/project, and one Azure AI Search resource. Skills live in `.github/skills/`.
Load the one that matches the task — you do not need to read them in order, and you should not
load more than one or two at a time. Depth lives in each skill's `references/`; load a
reference only when the task actually needs it.

**This table is the single routing surface for the pack. No skill restates it.**

| Task | Skill |
|---|---|
| Repo layout, topology choice, scaffolding, GA conformance review | `maf-voice-agent` |
| Agent/voice behaviour in YAML — instructions, model, tools, voice, VAD | `maf-agent-config` |
| VoiceLive realtime sessions, local microphone prototypes, VAD, barge-in, and voices | `voicelive-realtime` |
| The local reasoning agent — clients, tools, skills, sessions, retrieval | `maf-foundry-agent` |
| A second agent — multi-agent layout, Workflows, orchestration patterns | `maf-multi-agent-workflows` |
| Code-first chunking, embeddings, indexing, and live Azure AI Search checks | `foundry-iq` |
| Logging setup, DevUI, telemetry, or an agent that returns nothing | `maf-dev-loop` |
| Provision the Foundry resource/model or Azure AI Search | `microsoft-foundry` (user-scoped) |

Tooling skills, unrelated to MAF: `mermaid-diagrams` for any diagram work,
`skill-pack-audit` for reviewing this pack itself.

## House rules

These apply to **all** work in this repo, whether or not you loaded a skill. Each names the
skill that owns the detail — go there rather than re-deriving it.

1. **Behaviour is declarative, in MAF's own schema.** Agent behaviour lives in
   `config/agents/<name>.yaml` as a `kind: Prompt` document loaded by the shipped
   `AgentFactory`; workflows are `kind: Workflow` loaded by `WorkflowFactory`; only the
   VoiceLive session document is seed-owned. Python loads, validates, and constructs. A literal
   `instructions="..."`, a `ServerVad(threshold=...)` in `src/`, or a private pydantic model
   re-describing instructions/model/tools is a defect. → `maf-agent-config`
2. **The caller is untrusted input.** The primary input channel is a human speaking, and a
   caller can claim any identity or attempt prompt injection out loud. Bind identity, session
   ownership, and security filters from the *authenticated* session, never from a transcript.
   Retrieved documents are untrusted too — they never change tool selection or filters.
   → `maf-voice-agent`, `foundry-iq`
3. **One `build_<name>_agent(client, **deps) -> Agent` factory per agent.** It is what lets the
   voice loop, DevUI, and tests mount the same object. Never construct an agent at module
   scope. → `maf-foundry-agent`
4. **Agent Framework does not auto-load `.env`.** Call `load_dotenv()` once, at the process
   entry point. → `maf-foundry-agent`
5. **Two resources by default.** Runtime uses one Microsoft Foundry resource/project and one
   Azure AI Search service. The only permitted exception is an explicit `AZURE_VOICELIVE_*`
   override for an existing alternate VoiceLive deployment. Do not add project connections,
   App Insights, Storage, Cosmos DB, Redis, Content Understanding, memory stores, or a separate
   Azure OpenAI resource. → `maf-voice-agent`
6. **Match auth to the endpoint, and pick the client from the credential.** The Foundry
   *project* endpoint is Entra-only and needs the `Foundry User` data role; the *resource*
   endpoint and the VoiceLive websocket both accept the resource API key. A key-only
   subscription routes the MAF brain through `OpenAIChatClient` on `<resource>/openai/v1/`,
   not `FoundryChatClient`. Azure AI Search keys come from environment-backed settings. Never
   commit populated `.env` files. → `maf-foundry-agent`, `foundry-iq`, `voicelive-realtime`
7. **Three homes, no overlap.** `config/**.yaml` holds behaviour, env holds deployment values,
   `src/` holds code. A value in the wrong one is the most common defect in this repo.
   → `maf-voice-agent`
8. **A failure that cannot be explained is a defect.** `setup_logging()` runs before anything
   else at every entry point, startup validates every document and fails loudly, and no
   exception is swallowed in the voice dispatcher. The declarative loader drops unknown keys
   and builds unbound tools *silently*, so the seed must log the resolved model, the tool
   binding status, and the mounted stem at startup. → `maf-dev-loop`

Before declaring work complete, run the grep checklist in
`maf-voice-agent/references/conformance.md`.

## Editing these skills

A claim belongs in exactly one skill — the one that owns the SDK surface it describes.
Elsewhere, link to the owner. The only permitted second copy of a falsifiable fact is a row in
the conformance grep table. `skill-pack-audit` explains how to verify this holds.
