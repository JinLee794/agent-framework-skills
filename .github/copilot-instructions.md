## Repository Skills

This repo is a seed for Foundry-native voice agents built with Microsoft Agent Framework
(MAF) and Azure AI VoiceLive. Five skills live in `.github/skills/`. Load the one that
matches the task — you do not need to read them in order, and you should not load more than
one or two at a time. Depth lives in each skill's `references/`; load a reference only when
the task actually needs it.

| Task | Skill |
|---|---|
| GA rules, repo layout, topology choice, conformance review | `maf-voice-agent` |
| Agent/voice behaviour in YAML — instructions, model, tools, voice, VAD | `maf-agent-config` |
| VoiceLive realtime sessions, VAD, barge-in, voices, avatars | `voicelive-realtime` |
| The reasoning agent — clients, tools, skills, MCP, memory, retrieval, hosting | `maf-foundry-agent` |
| Local run/debug in DevUI, telemetry, keeping these skills current | `maf-dev-loop` |

Two rules apply to all work here, whether or not you loaded a skill:

1. **Behaviour is declarative.** Instructions, model, tools, voice, and VAD live in
   `config/**.yaml`, never as literals in Python. `maf-agent-config` has the contract.
2. **The caller is untrusted input.** Bind identity, memory `scope`, and security filters
   from the authenticated session, never from a transcript. `maf-voice-agent` has the rest of
   the non-negotiable GA rules.

<!-- mermaid-ai-skills:start -->
## Mermaid Diagrams

When the user asks to create, edit, or visualize a diagram, follow the
instructions in `.github/instructions/mermaid.instructions.md`.
<!-- mermaid-ai-skills:end -->
