---
name: voicelive-realtime
description: "Azure AI VoiceLive SDK (1.2.0, async-only): a guided interview that confirms managed-model vs Foundry-hosted BYOM before writing config, the managed model catalogue, local microphone/speaker prototypes, connect(), RequestSession, turn detection, barge-in, audio formats, voices, interim responses, and tools. Load for local VoiceLive audio or anything under src/voice. NOT for text-only DevUI debugging - load maf-dev-loop instead."
license: MIT
compatibility: Python 3.9+; azure-ai-voicelive[aiohttp]>=1.2.0; async-only; api-version 2026-04-10.
metadata: {author: MAFVoiceSeed, version: "2.6.1", last-reviewed: "2026-07-29", verified-against: "installed azure-ai-voicelive 1.2.0 (symbols, enum members, connect() signature, api-version default 2026-04-10) + Microsoft Learn Voice Live overview (supported models) and BYOM how-to"}
---

# VoiceLive Realtime — GA Patterns

## Start here

Any task that touches the VoiceLive connection or session begins with the
[configuration interview](#configuration-interview) below. Do not edit `.env`, the `voice`
section of `config/voice/<name>.yaml`, or `src/<package>/voice/` until the user has confirmed the
summary — a wrong model source fails at `connect()` with an error that looks nothing like its
cause.

For a runnable local full-duplex prototype using the device microphone and speakers, follow
[references/local-audio-prototype.md](references/local-audio-prototype.md). It isolates the
audio transport before adding the MAF brain and includes device preflight, threading,
barge-in, shutdown, and acceptance checks.

## Configuration interview

Ask these in order, one question per turn, using the editor's question tool so the user can
pick from options. Carry forward answers already stated in the conversation or already present
in `.env` — state what you found and ask for confirmation instead of re-asking blind. Stop and
ask whenever an answer would otherwise be inferred.

### Q1 — Model source

> VoiceLive can run a model it hosts for you, or a model deployment you own. Which one?
>
> - **Voice Live-managed** — pick from a pre-deployed catalogue. No deployment, no capacity
>   planning, no quota to arrange. Fastest way to a working call.
> - **Foundry-hosted (BYOM)** — VoiceLive calls a deployment in your Foundry resource.
>   Required for fine-tuned or provisioned-throughput deployments, for any model outside the
>   managed catalogue, and to reuse the exact deployment the local MAF brain already calls.

This repo's `.env.example` ships BYOM because its `FOUNDRY_MODEL` is not in the managed
catalogue. That is a default, not a constraint — say so rather than treating BYOM as settled.

### Q2 — Model identifier

Load [references/model-selection.md](references/model-selection.md) now and present the branch
matching Q1. Do not recite the whole catalogue; narrow it first.

**If managed:** ask for the priority, then offer the two or three matching identifiers with
their trade-off stated plainly.

| If the user cares most about | Offer | Say why |
|---|---|---|
| Interruption feel and latency | `gpt-realtime-1.5`, `gpt-realtime`, `gpt-realtime-mini` | Native speech-to-speech; no STT/TTS hops |
| Cost | `gpt-realtime-mini`, `gpt-5-mini`, `gpt-4.1-mini`, `gpt-5-nano` | Basic and lite pricing tiers |
| Reasoning quality | `gpt-5.4`, `gpt-5.2`, `gpt-5` | Cascaded, so budget extra latency |
| A specific Azure neural or custom voice | any cascaded model | Cascaded models reach the full Azure TTS catalogue |

Confirm the region supports the choice, and flag the three supported-but-not-pre-deployed
identifiers if the user names one — they need BYOM.

**If BYOM:** ask for the exact deployment name as it appears in the Foundry portal (not the
underlying model name), then confirm the profile that matches its API surface — realtime, chat
completion, or Anthropic messages.

### Q3 — Relationship to the local MAF brain

> Should VoiceLive use the same model value as the reasoning agent, or a different one?

Different values are normal and often correct: a cheap native model for the voice turn and a
stronger model for reasoning. Confirm it rather than letting the shared `FOUNDRY_MODEL`
fallback decide silently.

### Q4 — Resource

> Does VoiceLive run on the same Foundry resource as the project, or an existing separate one?

Same resource is the default and needs no `AZURE_VOICELIVE_ENDPOINT` / `AZURE_VOICELIVE_API_KEY`.
A separate resource needs both, set together. A BYOM deployment must live on whichever
resource is chosen here.

### Q5 — Voice and turn-taking

Only ask what the answers above actually constrain:

- **Voice** — if Q2 selected `azure-realtime`, the checked-in `azure_standard` voice must
  change to a dedicated native voice. Otherwise offer OpenAI vs Azure neural from
  [references/voices.md](references/voices.md).
- **Turn detection** — `server_vad` unless the user expects long natural pauses, which calls
  for a semantic VAD.
- **Interim response** — required in this topology; mandatory to keep for any cascaded model.

### Confirm before writing

Read the decision back as a table and wait for approval:

| Decision | Value |
|---|---|
| Source | Voice Live-managed / BYOM `<profile>` |
| VoiceLive model | `<identifier or deployment name>` |
| MAF brain model | `<deployment>` |
| Resource | primary Foundry / alternate VoiceLive |
| Voice | `<voice>` |
| Turn detection | `<vad>` |

### Apply the confirmed choice

Three files, no more. The answer-to-variable mapping is the table in
[references/model-selection.md](references/model-selection.md).

1. **`.env`** — set only the variables the answers require. `AZURE_VOICELIVE_PROFILE` is the
   switch: unset means managed, a `byom-*` value means BYOM. Leave the endpoint, key, and
   model overrides unset for the same-resource default, and mirror the outcome into
   `.env.example` — the profile active, the three overrides commented.
2. **the `session` section of `config/voice/<name>.yaml`** — voice, VAD, formats, and interim
   response. Model values never go here.
3. **`src/<package>/settings.py`** — only if a variable is genuinely new. The existing
   settings type already covers both sources; do not add a parallel switch.

Then state which values the user still has to supply, and how they will know it worked: a
successful `connect()` followed by `session.updated`.

## Install and connect

```bash
python -m pip install "azure-ai-voicelive[aiohttp]" python-dotenv
# audio samples additionally need pyaudio (portaudio19-dev / brew install portaudio)
```

The SDK is **async-only** since `1.0.0`. There is no sync client.

```python
from azure.ai.voicelive.aio import connect
from azure.core.credentials import AzureKeyCredential

endpoint, api_key, model, query = resolve_voicelive_settings()

async with connect(
    endpoint=endpoint,
    credential=AzureKeyCredential(api_key),
    model=model,
    query=query,
) as connection:
    ...
```

`resolve_voicelive_settings()` defaults to the primary Foundry resource:

```python
def foundry_resource_endpoint(project_endpoint: str) -> str:
    marker = "/api/projects/"
    if marker not in project_endpoint:
        raise ValueError("FOUNDRY_PROJECT_ENDPOINT must contain /api/projects/<project>")
    return project_endpoint.split(marker, 1)[0].rstrip("/")


def resolve_voicelive_settings() -> tuple[str, str, str, dict[str, str] | None]:
    override_endpoint = os.getenv("AZURE_VOICELIVE_ENDPOINT")
    override_key = os.getenv("AZURE_VOICELIVE_API_KEY")
    if bool(override_endpoint) != bool(override_key):
        raise ValueError("AZURE_VOICELIVE_ENDPOINT and AZURE_VOICELIVE_API_KEY must be set together")
    profile = os.getenv("AZURE_VOICELIVE_PROFILE")
    return (
        override_endpoint or foundry_resource_endpoint(os.environ["FOUNDRY_PROJECT_ENDPOINT"]),
        override_key or os.environ["FOUNDRY_API_KEY"],
        os.getenv("AZURE_VOICELIVE_MODEL") or os.environ["FOUNDRY_MODEL"],
        {"profile": profile} if profile else None,
    )
```

Every `AZURE_VOICELIVE_*` value is an optional override. Unset `AZURE_VOICELIVE_PROFILE` means
a Voice Live-managed model on the primary Foundry resource; a `byom-*` value selects BYOM.

### Credentials

The realtime websocket accepts **either** credential. `AzureKeyCredential` sends the resource
key as the `api-key` header; a token credential sends `Authorization: Bearer` and additionally
requires the `Cognitive Services User` **and** `Foundry User` roles on the resource, with the
`https://ai.azure.com/.default` scope.

| Endpoint | Shape | API key | Entra |
|---|---|---|---|
| VoiceLive websocket | `wss://<resource>.services.ai.azure.com/voice-live/realtime` | yes — `AzureKeyCredential` | yes |
| Foundry **project** | `https://<resource>.services.ai.azure.com/api/projects/<project>` | **never accepted** | required |
| Foundry **resource** OpenAI | `https://<resource>.services.ai.azure.com/openai/v1/` | yes — `api_key=` | yes |

The same key that authenticates VoiceLive also works on the resource-level OpenAI surface, but
**never** on the project endpoint: that path is Entra-only and needs a data-plane role, so a
key-only subscription must not route the MAF brain through it. Picking the matching chat client
is owned by [maf-foundry-agent](../maf-foundry-agent/SKILL.md).

`connect()` defaults to `api_version="2026-04-10"`. Transport tuning is **not** passed as
keyword arguments to `connect()` — it goes in the `connection_options` mapping
(`WebsocketConnectionOptions`), whose keys are `receive_timeout`, `close_timeout`,
`handshake_timeout`, `heartbeat`, `autoping`, `autoclose`, `max_msg_size`, `compression`
(bool or zlib window int), and `vendor_options` as an escape hatch:

```python
from azure.ai.voicelive.aio import WebsocketConnectionOptions

async with connect(
    ...,
    connection_options=WebsocketConnectionOptions(receive_timeout=30, close_timeout=5),
) as connection:
    ...
```

Do not reach into the underlying websocket directly.

## Responder topology

This seed supports `maf_bridge` only. The bridge's local MAF brain uses the project endpoint;
VoiceLive remains the realtime transport.

## Model source

Settled by [Q1](#q1--model-source) and [Q2](#q2--model-identifier) of the interview. In short:

| VoiceLive path | What `connect(model=)` means | Additional connection input |
|---|---|---|
| Voice Live-managed | A model identifier pre-deployed by Voice Live | None |
| Foundry-hosted (BYOM) | The exact name of a model deployment in the Foundry resource | `query={"profile": "<byom-mode>"}` |

Never infer the path from a model-looking value such as `gpt-5.4`; the same family can be
reachable either way. The catalogue, profiles, tiers, and the answer-to-`.env` mapping live in
[references/model-selection.md](references/model-selection.md).

## Session configuration

Session shape is **not** hand-written here — it is loaded from the `voice` section of
`config/voice/<name>.yaml` and built by `src/<package>/config/builders.py`. The full `RequestSession`
field map, model-selection table, and a worked construction example are in
[references/session-config.md](references/session-config.md).

Three traps that are not obvious from the field map:

- `OutputAudioFormat` values use underscores: `pcm16_8000hz`, `pcm16_16000hz`. Hyphenated
  legacy values still deserialize but must never be written.
- To explicitly disable a feature, set it to `None`. `RequestSession` serializes explicit
  `None` (since `1.2.0b3`), so `turn_detection=None` correctly sends `"turn_detection": null`.
- Echo cancellation is essential whenever playback and capture share a device; without it
  the agent interrupts itself.

## Turn detection and end-of-utterance

| Class | Use when |
|---|---|
| `ServerVad` | Default. Energy-based; tune `threshold`, `prefix_padding_ms`, `silence_duration_ms` |
| `AzureSemanticVad` | Semantic turn-taking; tolerates natural pauses better than energy VAD |
| `AzureSemanticVadEn` / `AzureSemanticVadMultilingual` | Language-scoped variants |

Semantic end-of-utterance detection attaches to VAD via `end_of_utterance_detection`:

```python
from azure.ai.voicelive.models import (
    AzureSemanticDetectionEn, AzureSemanticVad, EouThresholdLevel,
)

turn_detection = AzureSemanticVad(
    threshold=0.5,
    prefix_padding_ms=300,
    silence_duration_ms=500,
    end_of_utterance_detection=AzureSemanticDetectionEn(
        threshold_level=EouThresholdLevel.DEFAULT,
        timeout_ms=2000,
    ),
)
```

Renames to watch for in older code: `EOUDetection` → `EouDetection`,
`AzureMultilingualSemanticVad` → `AzureSemanticVadMultilingual`, and semantic detection now
takes `threshold_level`/`timeout_ms` rather than `threshold`/`timeout`.

## Event loop and barge-in

Barge-in is the single most commonly broken behaviour. Handle it explicitly.

```python
from azure.ai.voicelive.models import ServerEventType

async for event in connection:
    if event.type == ServerEventType.SESSION_UPDATED:
        session_id = event.session.id
        await audio.start_capture()

    elif event.type == ServerEventType.INPUT_AUDIO_BUFFER_SPEECH_STARTED:
        # 1. discard local playback immediately
        await audio.stop_playback()
        # 2. tell the service to abandon the in-flight response
        await connection.response.cancel()

    elif event.type == ServerEventType.RESPONSE_AUDIO_DELTA:
        await audio.enqueue(event.delta)

    elif event.type == ServerEventType.RESPONSE_DONE:
        ...

    elif event.type == ServerEventType.ERROR:
        logger.error("VoiceLive error: %s", event.error)

    elif event.type == ServerEventType.WARNING:
        logger.warning("VoiceLive warning: %s", event.warning)
```

Notes:

- Both barge-in steps are required. Local invalidation discards audio already received;
    response cancellation stops the service from generating more of it.
- Do not cancel an in-flight local bridge-tool task on barge-in. VoiceLive still requires a
    `FunctionCallOutputItem` for that call. Send the output, but suppress its follow-up
    `response.create()` when a newer caller turn has started.
- `ServerEventType.WARNING` was added in `1.2.0b4`; handle it so non-fatal issues are visible.
- Do not `break` out of the loop on `RESPONSE_DONE` in a live conversation — it ends the
  session. Only sample/one-shot scripts do that.
- Catch `ConnectionClosed` (a subclass of the SDK's `ConnectionError`) and reconnect with
  `conversation_id` to resume rather than starting a fresh conversation. Both are imported
  from `azure.ai.voicelive.aio`, not the package root.

## Function tools

```python
from azure.ai.voicelive.models import FunctionTool, RequestSession, ToolChoiceLiteral

tools = [
    FunctionTool(
        name="ask_agent",
        description="Answer the caller by dispatching to the local MAF agent.",
        parameters={
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "The caller's question"}
            },
            "required": ["question"],
        },
    )
]
session = RequestSession(..., tools=tools, tool_choice=ToolChoiceLiteral.REQUIRED)
```

The bridge tool is mandatory in this topology. `AUTO` can complete a caller turn without
dispatching to the local MAF agent.

Dispatch a completed call from either `RESPONSE_FUNCTION_CALL_ARGUMENTS_DONE` or a
`ResponseFunctionCallItem` carried by `RESPONSE_OUTPUT_ITEM_DONE`. Backends can emit both,
so deduplicate them by `call_id` before invoking the local agent.

Handle the call by creating a function-call output item and requesting a new response:

```python
from azure.ai.voicelive.models import FunctionCallOutputItem

result = await dispatch(name, json.loads(arguments))
await connection.conversation.item.create(
    item=FunctionCallOutputItem(call_id=call_id, output=json.dumps(result))
)
await connection.response.create()
```

`output` must be a JSON **string**, not a dict. Keep tool latency under ~1s or pair it with
an interim response.

## Interim responses (required for the `maf_bridge` topology)

Cover model or tool latency so the caller is never in silence:

```python
from azure.ai.voicelive.models import (
    InterimResponseTrigger, LlmInterimResponseConfig, RequestSession,
    StaticInterimResponseConfig,
)

session = RequestSession(
    ...,
    interim_response=StaticInterimResponseConfig(
        triggers=[InterimResponseTrigger.TOOL, InterimResponseTrigger.LATENCY],
        texts=["Let me check that for you.", "One moment."],
    ),
)
```

`LlmInterimResponseConfig` generates context-aware filler instead of sampling static texts;
it costs an extra model call, so prefer static text for high-volume telephony.

## Voices

Native-audio models (`gpt-realtime*`) give the lowest latency and accept either an OpenAI
voice or an Azure TTS voice; `azure-realtime` accepts only its dedicated native voices.
Cascaded models reach the full Azure neural and custom catalogue but add STT and TTS hops.
Custom voice is a limited-access feature.

Full voice catalogue and `AzurePersonalVoice` options:
[references/voices.md](references/voices.md).

## Tracing

Voice tracing is opt-in and lives in the SDK, not in Agent Framework:

```python
os.environ["AZURE_EXPERIMENTAL_ENABLE_GENAI_TRACING"] = "true"
from azure.ai.voicelive.telemetry import VoiceLiveInstrumentor
VoiceLiveInstrumentor().instrument()
```

Launch DevUI with its instrumentation flag or use a local console exporter before calling
`instrument()`. Emitted `gen_ai.voice.*` attributes and correlation with `invoke_agent` spans
are covered by [maf-dev-loop](../maf-dev-loop/SKILL.md).

## References

| Task | Reference |
|---|---|
| Managed catalogue, BYOM profiles, answer-to-`.env` mapping | [references/model-selection.md](references/model-selection.md) |
| Local microphone/speaker rapid prototype | [references/local-audio-prototype.md](references/local-audio-prototype.md) |
| `RequestSession` field map, telephony profile, migration table | [references/session-config.md](references/session-config.md) |
| Voice catalogue | [references/voices.md](references/voices.md) |

