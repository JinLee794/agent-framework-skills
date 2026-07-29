---
name: maf-agent-config
description: "The YAML behaviour contract: agent.yaml, voice.yaml, profiles, extends, ${ENV} and {{ runtime.* }} placeholders, config/ layout. Load before adding or changing any agent instruction, model, tool list, voice, or VAD setting."
license: MIT
compatibility: Python 3.10+; pydantic v2; PyYAML; agent-framework-foundry; azure-ai-voicelive (see voicelive-realtime).
metadata:
  author: MAFVoiceSeed
  version: "2.3.0"
  last-reviewed: "2026-07-29"
  verified-against: "pydantic 2.x; PyYAML 6.x; repo convention. SDK field names cross-checked against maf-foundry-agent and voicelive-realtime."
---

# Agent & Voice Configuration — YAML Contract

**Behaviour lives in YAML. Python is wiring.**

If changing a value would change what the agent *says or does* — instructions, model,
temperature, which tools are attached, the voice, VAD thresholds, interim phrases — it is a
YAML value. Python may only load, validate, and construct. That is what makes a POC
reviewable: a stakeholder reads one YAML file and knows the entire behaviour.

## What goes where

Three homes, no overlap. Most config bugs are a value in the wrong one.

| Value | Home |
|---|---|
| Instructions, model deployment, temperature, tool list, voice, VAD, interim responses | `config/**.yaml` |
| Endpoints, resource names, credentials, connection strings | env → `settings.py` |
| Tool *implementations*, event loop, audio I/O, orchestration | `src/` |

`settings.py` is the only reader of `os.environ`. YAML references env by name
(`${FOUNDRY_MODEL}`); the loader resolves through `settings`, not a second scattered
`os.environ` call.

## Layout

```text
config/
  agents/
    _base.agent.yaml           # shared defaults; never referenced directly by code
    concierge.agent.yaml
  voice/
    _base.voice.yaml
    concierge.voice.yaml       # desktop/WebRTC profile
    telephony.voice.yaml       # G.711 profile, extends _base
  profiles/
    local.yaml                 # environment overlays, applied last
    prod.yaml
  schemas/
    agent.schema.json          # generated from the pydantic models
    voice.schema.json
```

Naming is load-bearing: `<name>.agent.yaml` / `<name>.voice.yaml`. The stem is the id used
everywhere else. Files prefixed `_` are fragments — the loader refuses them as top-level.

## Agent YAML

```yaml
# yaml-language-server: $schema=../schemas/agent.schema.json
name: concierge
description: Phone concierge that looks up and cancels bookings.

model:
  deployment: ${FOUNDRY_MODEL}
  temperature: 0.3
  max_output_tokens: 800

instructions: |
  You are a concise phone concierge.
  Confirm the booking code back to the caller before any change.
  If you do not know something, say so and offer to transfer.

tools:
  - ref: booking.get_booking            # resolved from the tool registry
    approval: never_require
  - ref: booking.cancel_booking
    approval: always_require

skills:
  paths: ["skills/"]
  auto_approve_read_only: true
```

- `tools[].ref` is `<module>.<function>` inside `src/<package>/tools/`, resolved through an
  explicit registry. YAML never imports; it names.
- `approval` is **required** on every `ref` tool. The loader raises if omitted — no default,
  because a default hides the "forgot the approval mode" bug.
- Azure AI Search context providers are constructed by the loader, not the agent module.

Full field map: [references/agent-yaml.md](references/agent-yaml.md).

## Voice YAML

One file describes a complete VoiceLive session, mapping 1:1 onto `RequestSession` — same
concepts, snake_case keys, no invented abstractions.

```yaml
# yaml-language-server: $schema=../schemas/voice.schema.json
extends: _base.voice.yaml

topology: maf_bridge
agent: concierge              # -> config/agents/concierge.agent.yaml

session:
  modalities: [text, audio]
  voice:
    type: azure_standard
    name: en-US-AvaNeural
  audio:
    input_format: pcm16
    output_format: pcm16
    echo_cancellation: true
    noise_reduction: true
    transcription:
      model: whisper-1
  turn_detection:
    type: server_vad
    threshold: 0.5
    prefix_padding_ms: 300
    silence_duration_ms: 500
  interim_response:
    type: static
    triggers: [tool]
    texts:
      - "Let me check that for you."
      - "One moment."
  limits:
    max_response_output_tokens: 400
    temperature: 0.6
```

- The loader accepts only `maf_bridge` in this seed and requires both `interim_response` and
  an `agent` reference.
- `connection` is optional. Endpoint, key, and model inherit from the primary Foundry settings;
  `AZURE_VOICELIVE_*` environment values are deployment overrides, not YAML behaviour.
- Enum-ish values are lowercase snake_case and mapped to SDK enums by the loader. The full
  YAML-key → SDK-type mapping, including the audio format spellings, is owned by
  `voicelive-realtime`; the loader must reject anything not in it.
- `turn_detection: ~` is meaningful (client-driven turn taking) and must be written
  explicitly. Omission inherits from `_base`.

Full field map and SDK type mapping: [references/voice-yaml.md](references/voice-yaml.md).

## Composition

`extends` + environment overlay. Deep merge, last write wins; lists replace, they do not append.

```text
_base.voice.yaml  →  telephony.voice.yaml  →  profiles/prod.yaml
```

```yaml
# config/profiles/prod.yaml — overlay only, never a complete config
agents:
  concierge:
    model:
      temperature: 0.1
voice:
  telephony:
    session:
      turn_detection:
        silence_duration_ms: 400
```

Select the overlay through the application startup profile. Do not fork whole files per
environment — that is how a prod agent silently keeps a dev prompt.

## Placeholders

Two syntaxes, deliberately different: they resolve at different times and one is a security
boundary.

| Syntax | Resolved | Source | Use for |
|---|---|---|---|
| `${VAR}` | at load, once | `settings` (env) | endpoints, deployment names, resource ids |
| `${VAR:-default}` | at load | env with fallback | optional tuning |
| `{{ runtime.x }}` | per request | the call/session context object | user id, tenant, locale, session id |

- **Never put a secret in YAML**, not even as a default. `${...}` names a variable; it never
  carries a value.
- An unset `${VAR}` is a startup error, not an empty string. Fail at boot, not mid-call.
- `{{ runtime.* }}` comes from **authenticated** context only. `scope: "{{ runtime.user_id }}"`
  is correct; binding it from a spoken name or client-supplied field is a cross-tenant leak.

## Loading

```python
from mypkg.config import load_agent_config, load_voice_config, build_agent, build_session

agent_cfg = load_agent_config("concierge")               # validated, placeholders resolved
agent = build_agent(agent_cfg, client=client, runtime={"user_id": caller_id})

voice_cfg = load_voice_config("telephony")
session = build_session(voice_cfg)                       # -> RequestSession
```

Validation requirements — all of these:

- Pydantic v2 models with `model_config = ConfigDict(extra="forbid")`. A misspelled
  `silence_duration_ms` must be a startup error, not a silently ignored key.
- Validate **all** configs at startup, not lazily. A POC that dies on the first phone call
  instead of at boot is a bad demo.
- Generate `config/schemas/*.json` from the same models via `model_json_schema()` and commit
  them. The `# yaml-language-server: $schema=` comment then gives completion and inline errors
  in VS Code — that is most of the "easily workable" requirement.

## POC fast path

1. Copy `_base.agent.yaml` → `<name>.agent.yaml`; write `instructions` and the tool list.
2. Add each `ref` tool to `src/<package>/tools/` with tests. Register it.
3. Copy a voice profile; set `topology: maf_bridge`, `agent`, and the voice.
4. Run it through DevUI (`entities/` reuses `build_agent`) to check reasoning before audio.
5. Only then run the voice loop.

Steps 1–4 need no new Python beyond tool bodies. If a POC requires editing `src/` to change
behaviour, the config contract has been broken.

## Anti-patterns

| Pattern | Verdict |
|---|---|
| `instructions="..."` literal in a Python agent module | Move to YAML |
| `ServerVad(threshold=0.5, ...)` constructed in `voice/` | Move to YAML; loader builds it |
| `os.environ[...]` inside a loader or agent module | Route through `settings` |
| A secret, key, or connection string in any `config/**.yaml` | Remove; use `${VAR}` |
| Pydantic model without `extra="forbid"` | Typos become silent no-ops |
| Config parsed lazily on first request | Validate all configs at startup |
| A full copy of a config per environment | Use `extends` + `profiles/` overlay |
| `ref` tool without `approval` | Loader must raise |
| Any topology other than `maf_bridge` | Project-backed and hosted topologies require token authentication |
| `topology: maf_bridge` without `interim_response` | Dead air during the agent run |
| Committed `*.schema.json` out of sync with the models | Regenerate in CI and diff |
