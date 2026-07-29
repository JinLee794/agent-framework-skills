---
name: voicelive-realtime
description: "Azure AI VoiceLive SDK (1.2.0, async-only): managed-model vs Foundry-hosted BYOM selection, local microphone/speaker prototypes, connect(), RequestSession, turn detection, barge-in, audio formats, voices, avatars, interim responses, and tools. Load for local VoiceLive audio or anything under src/voice. NOT for text-only DevUI debugging - load maf-dev-loop instead."
license: MIT
compatibility: Python 3.9+; azure-ai-voicelive[aiohttp]>=1.2.0; async-only; api-version 2026-04-10.
metadata: {author: MAFVoiceSeed, version: "2.4.0", last-reviewed: "2026-07-29", verified-against: "azure-ai-voicelive 1.2.0 (GA, api-version 2026-04-10) changelog + Microsoft VoiceLive Python model quickstart + Voice Live BYOM guidance"}
---

# VoiceLive Realtime — GA Patterns

## Start here

For a runnable local full-duplex prototype using the device microphone and speakers, follow
[references/local-audio-prototype.md](references/local-audio-prototype.md). It isolates the
audio transport before adding the MAF brain and includes device preflight, threading,
barge-in, shutdown, and acceptance checks.

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

The `AZURE_VOICELIVE_*` values are optional overrides. Leave them unset for a Voice
Live-managed model on the primary Foundry resource. Set `AZURE_VOICELIVE_PROFILE` only for
BYOM. Project chat still uses Entra; never pass the resource key to `FoundryChatClient`.

`connect()` also accepts transport tuning: `receive_timeout`, `close_timeout`,
`handshake_timeout`, `compression` (bool or zlib window int), and `vendor_options` as an
escape hatch. Do not reach into the underlying websocket directly.

## Responder topology

This seed supports `maf_bridge` only. The bridge's local MAF brain uses the project endpoint;
VoiceLive remains the realtime transport.

## Choose the VoiceLive model source first

The model used by the local MAF brain and the model used by VoiceLive are separate decisions,
even when both call sites currently read `FOUNDRY_MODEL`.

| VoiceLive path | What `connect(model=)` means | Additional connection input |
|---|---|---|
| Voice Live-managed | A model identifier pre-deployed by Voice Live | None |
| Foundry-hosted (BYOM) | The exact name of a model deployment in the Foundry resource | `query={"profile": "<byom-mode>"}` |

Before editing code or configuration, ask the user to confirm which path they intend whenever
it is not explicit. Never infer the path from a model-looking value such as `gpt-5.4`; the
same family can be available through either path. Also confirm whether the local MAF deployment
and VoiceLive model are intended to use the same value.

The primary path uses one Foundry resource. If the user explicitly selects an alternate
VoiceLive deployment, set the optional endpoint/key pair; the selected BYOM deployment must
live with that VoiceLive resource. This seed does not add `foundry-resource-override` for a
third model resource. Use `AZURE_VOICELIVE_MODEL` when the two model roles differ and
`AZURE_VOICELIVE_PROFILE` for BYOM. See [references/session-config.md](references/session-config.md).

## Session configuration

Session shape is **not** hand-written here — it is loaded from
`config/voice/<name>.voice.yaml` and built by `src/<package>/config/builders.py`. The full
`RequestSession` field map, model-selection table, and a worked construction example are in
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

## Voices and avatars

Voice choice constrains model choice: native-audio models (`gpt-realtime`,
`gpt-realtime-mini`, `azure-realtime`) give the lowest latency but only OpenAI voices; Azure
neural and custom voices route through Azure STT/TTS, which costs latency. Custom voice and
custom avatar are limited-access features.

Full voice catalogue, `AzurePersonalVoice` options, the `AvatarConfig.avatar_type` rename in
`1.2.0`, and the avatar event contract:
[references/voices-and-avatars.md](references/voices-and-avatars.md).

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
| Local microphone/speaker rapid prototype | [references/local-audio-prototype.md](references/local-audio-prototype.md) |
| Full session-config matrix, model selection, migration table | [references/session-config.md](references/session-config.md) |
| Voice catalogue and avatars | [references/voices-and-avatars.md](references/voices-and-avatars.md) |

