---
name: voicelive-realtime
description: "Azure AI VoiceLive SDK (1.2.0, async-only): connect(), RequestSession, turn detection and end-of-utterance, barge-in, audio formats, voices, avatars, interim responses, voice function and MCP tools. Load for anything under src/voice."
license: MIT
compatibility: Python 3.9+; azure-ai-voicelive[aiohttp]>=1.2.0; async-only; api-version 2026-04-10.
metadata:
  author: MAFVoiceSeed
  version: "2.0.0"
  verified-against: "azure-ai-voicelive 1.2.0 GA changelog + samples"
---

# VoiceLive Realtime — GA Patterns

## Install and connect

```bash
python -m pip install "azure-ai-voicelive[aiohttp]" azure-identity python-dotenv
# audio samples additionally need pyaudio (portaudio19-dev / brew install portaudio)
```

The SDK is **async-only** since `1.0.0`. There is no sync client.

```python
from azure.ai.voicelive.aio import connect
from azure.identity.aio import DefaultAzureCredential

async with DefaultAzureCredential() as credential:
    async with connect(
        endpoint=os.environ["AZURE_VOICELIVE_ENDPOINT"],
        credential=credential,
        model="gpt-realtime",
    ) as connection:
        ...
```

`AzureKeyCredential` is supported for local development only. Prefer Entra ID everywhere else.

`connect()` also accepts transport tuning: `receive_timeout`, `close_timeout`,
`handshake_timeout`, `compression` (bool or zlib window int), and `vendor_options` as an
escape hatch. Do not reach into the underlying websocket directly.

## Connecting a Foundry agent as the responder (topology A)

`FoundryAgentTool` was **removed in 1.2.0**. Configure the agent at connection time:

```python
async with connect(
    endpoint=endpoint,
    credential=credential,
    agent_name=os.environ["FOUNDRY_AGENT_NAME"],       # required
    project_name=os.environ["FOUNDRY_PROJECT_NAME"],   # required
    agent_version=os.getenv("FOUNDRY_AGENT_VERSION"),  # optional
    conversation_id=existing_conversation_id,          # optional, resumes a conversation
    authentication_identity_client_id=uami_client_id,  # optional
) as connection:
    ...
```

Do not also send `instructions`/`tools` in `session.update` for this topology — the agent
definition is authoritative and the extra payload is misleading.

## Session configuration

In this repo, session shape is **not** hand-written — it is loaded from
`config/voice/<name>.voice.yaml` and built by `src/<package>/config/builders.py`. See
[maf-agent-config](../maf-agent-config/SKILL.md). The Python below is what the builder
produces, and is the reference for what each YAML key means.

```python
from azure.ai.voicelive.models import (
    AudioEchoCancellation,
    AudioInputTranscriptionOptions,
    AudioNoiseReduction,
    AzureStandardVoice,
    InputAudioFormat,
    Modality,
    OutputAudioFormat,
    RequestSession,
    ServerVad,
)

session = RequestSession(
    modalities=[Modality.TEXT, Modality.AUDIO],
    instructions="You are a concise, friendly phone concierge.",
    voice=AzureStandardVoice(name="en-US-AvaNeural", type="azure-standard"),
    input_audio_format=InputAudioFormat.PCM16,
    output_audio_format=OutputAudioFormat.PCM16,
    input_audio_echo_cancellation=AudioEchoCancellation(),
    input_audio_noise_reduction=AudioNoiseReduction(),
    input_audio_transcription=AudioInputTranscriptionOptions(model="whisper-1"),
    turn_detection=ServerVad(threshold=0.5, prefix_padding_ms=300, silence_duration_ms=500),
)
await connection.session.update(session=session)
```

Rules:

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
        # 1. stop local playback immediately
        await audio.stop_playback()
        # 2. tell the service to abandon the in-flight response
        await connection.response.cancel()
        # 3. clear anything already buffered for output
        await connection.output_audio_buffer.clear()

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

- All three barge-in steps are required. Stopping only local playback leaves the service
  generating audio you have already discarded, which corrupts the next turn's timing.
- `ServerEventType.WARNING` was added in `1.2.0b4`; handle it so non-fatal issues are visible.
- Do not `break` out of the loop on `RESPONSE_DONE` in a live conversation — it ends the
  session. Only sample/one-shot scripts do that.
- Catch `ConnectionClosed` (subclass of the SDK's `ConnectionError`) and reconnect with
  `conversation_id` to resume rather than starting a fresh conversation.

## Function tools

```python
from azure.ai.voicelive.models import FunctionTool, ToolChoiceLiteral

tools = [
    FunctionTool(
        name="get_booking",
        description="Look up a booking by confirmation code.",
        parameters={
            "type": "object",
            "properties": {"code": {"type": "string", "description": "Confirmation code"}},
            "required": ["code"],
        },
    )
]
session = RequestSession(..., tools=tools, tool_choice=ToolChoiceLiteral.AUTO)
```

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

## Interim responses (required for topology B)

Cover model or tool latency so the caller is never in silence:

```python
from azure.ai.voicelive.models import (
    InterimResponseTrigger, LlmInterimResponseConfig, StaticInterimResponseConfig,
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

## MCP tools

VoiceLive can call remote MCP servers directly. Approval flow is controlled by
`MCPApprovalType` (`never`, `always`, or per-tool). Use `always` for anything with side
effects and handle the approval-request server events by sending an approval response.
Never auto-approve tools from a server you do not control.

## Voices

- Azure neural: `AzureStandardVoice(name="en-US-AvaNeural", type="azure-standard")`.
  Also `en-US-JennyNeural`, `en-US-GuyNeural`.
- OpenAI: pass the name as a string — `alloy`, `echo`, `fable`, `onyx`, `nova`, `shimmer`,
  and (added in `1.2.0b2`) `marin`, `cedar`. The enum is `OpenAIVoiceName` (renamed from `OAIVoice`).
- Custom/personal: `AzurePersonalVoice` supports `custom_lexicon_url`, `prefer_locales`,
  `locale`, `style`, `pitch`, `rate`, `volume`. Custom voice and custom avatar are
  limited-access features — confirm eligibility before designing around them.

Native-audio models (`gpt-realtime`, `gpt-realtime-mini`, `azure-realtime`) give the lowest
latency. Text models (`gpt-5.x`, `gpt-4.1`) route through Azure STT/TTS, which is what
enables Azure neural and custom voices.

## Avatars

`AvatarConfig` renamed its `type` field to `avatar_type` in `1.2.0` to avoid shadowing the
builtin. Supported kinds are `video-avatar` and `photo-avatar` (`AvatarConfigTypes`), with
`AvatarOutputProtocol` of `webrtc` or `websocket`. Use `Scene` for zoom/position/rotation.
Drive UI state from `ServerEventSessionAvatarSwitchToSpeaking` /
`...SwitchToIdle` and render frames from `ServerEventResponseVideoDelta`.

## Tracing

Voice tracing is opt-in and lives in the SDK, not in Agent Framework:

```python
os.environ["AZURE_EXPERIMENTAL_ENABLE_GENAI_TRACING"] = "true"
from azure.ai.voicelive.telemetry import VoiceLiveInstrumentor
VoiceLiveInstrumentor().instrument()
```

Emits `gen_ai.voice.*` attributes including `session_id`, `first_token_latency_ms`,
`turn_count`, `interruption_count`, `audio_bytes_sent`/`received`. Configure the exporter
*before* calling `instrument()` — it reuses whatever tracer provider is registered. Exporter
wiring, the full attribute catalogue, and correlating these spans with `invoke_agent` spans:
[maf-dev-loop](../maf-dev-loop/SKILL.md).

## Reference

Deeper configuration notes, model selection, and a full session-config matrix are in
[references/session-config.md](references/session-config.md).
