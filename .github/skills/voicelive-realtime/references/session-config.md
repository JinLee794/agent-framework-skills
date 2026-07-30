# VoiceLive Session Configuration — Reference

Model source, the managed catalogue, BYOM profiles, and the answer-to-`.env` mapping are owned
by [model-selection.md](model-selection.md). Settle those with the user first — the session
fields below assume the model and its audio path are already confirmed.

`reasoning_effort` (`ReasoningEffort`) is settable on the session for reasoning-capable
models. For voice, keep it low — reasoning latency is audible.

## `RequestSession` field map

| Field | Type | Guidance |
|---|---|---|
| `modalities` | `list[Modality]` | `[TEXT, AUDIO]` for speech-out; `[TEXT]` for text-only tests |
| `instructions` | `str` | Bridge-routing instructions built from the checked-in voice YAML |
| `voice` | `AzureStandardVoice` \| `AzureCustomVoice` \| `AzurePersonalVoice` \| `str` | String selects an OpenAI voice |
| `input_audio_format` | `InputAudioFormat` | `PCM16`, `G711_ULAW`, `G711_ALAW` |
| `output_audio_format` | `OutputAudioFormat` | `PCM16`, `PCM16_8000HZ`, `PCM16_16000HZ`, `G711_ULAW`, `G711_ALAW` |
| `input_audio_echo_cancellation` | `AudioEchoCancellation` | Required for shared-device capture/playback |
| `input_audio_noise_reduction` | `AudioNoiseReduction` | Recommended for telephony |
| `input_audio_transcription` | `AudioInputTranscriptionOptions` | Needed if you want user transcripts |
| `turn_detection` | `ServerVad` \| `AzureSemanticVad*` \| `None` | `None` = client-driven turn taking |
| `tools` | `list[Tool]` | One local `FunctionTool` that dispatches to the MAF agent |
| `tool_choice` | `ToolChoiceLiteral` \| `ToolChoiceFunctionObject` | `ToolChoiceObject` was renamed to `ToolChoiceFunctionObject` |
| `interim_response` | `StaticInterimResponseConfig` \| `LlmInterimResponseConfig` | Cover tool/model latency |
| `animation` | `AnimationOptions` | Viseme/blendshape output |
| `max_response_output_tokens` | `int` \| `"inf"` | Cap runaway responses |
| `temperature` | `float` | Keep low for task-oriented voice agents |
| `reasoning_effort` | `ReasoningEffort` | Low for latency-sensitive voice |
| `metadata` | `dict[str, str]` | Correlate turns with your own request IDs |

### Worked construction

What `src/<package>/config/builders.py` produces from the `voice` section of
`config/voice/<name>.yaml`. Never hand-write this in application code.

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
    input_audio_noise_reduction=AudioNoiseReduction(type="near_field"),
    input_audio_transcription=AudioInputTranscriptionOptions(model="azure-speech"),
    turn_detection=ServerVad(threshold=0.5, prefix_padding_ms=300, silence_duration_ms=500),
)
await connection.session.update(session=session)
```

## Telephony profile (G.711)

```python
session = RequestSession(
    modalities=[Modality.TEXT, Modality.AUDIO],
    input_audio_format=InputAudioFormat.G711_ULAW,
    output_audio_format=OutputAudioFormat.G711_ULAW,
    input_audio_noise_reduction=AudioNoiseReduction(type="near_field"),
    turn_detection=ServerVad(threshold=0.6, prefix_padding_ms=200, silence_duration_ms=400),
    interim_response=StaticInterimResponseConfig(
        triggers=[InterimResponseTrigger.TOOL],
        texts=["One moment."],
    ),
)
```

Tighter VAD thresholds suit noisy phone lines. Do not resample G.711 client-side; let the
service handle format negotiation.

## Transcription

Cascaded pipelines accept `azure-speech`, `azure-mrs`, `mai-transcribe-1`,
`mai-transcribe-1.5`, or `mai-transcribe`. They reject `whisper-1` during the session update.

`TranscriptionPhrase` and `TranscriptionWord` (added in `1.2.0`) carry per-phrase and
per-word timing and, with diarization-capable models (`gpt-4o-transcribe-diarize`,
`mai-transcribe-1`), speaker labels. Use `SessionIncludeOption` to request the extra fields
rather than parsing them out of raw events.

Transcripts are PII. Do not log them unless
`OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` is deliberately enabled in a
non-production environment.

## Audio buffer resources

| Resource | Methods | Use |
|---|---|---|
| `connection.input_audio_buffer` | `append`, `commit`, `clear` | Push captured PCM; `commit` only when `turn_detection=None` |
| `connection.response` | `create`, `cancel` | Request or abandon a response |
| `connection.conversation.item` | `create`, `delete`, `truncate`, `retrieve` | Manage conversation items |
| `connection.session` | `update` | Apply session configuration |

With server VAD enabled, never call `input_audio_buffer.commit()` — the service commits on
speech-stop and an extra commit produces empty-buffer errors.

## Error handling

```python
from azure.ai.voicelive import ConnectionClosed, ConnectionError

try:
    async with connect(...) as connection:
        await run_loop(connection)
except ConnectionClosed as exc:
    logger.warning("VoiceLive closed: %s", exc)
    # reconnect, passing conversation_id to resume
except ConnectionError as exc:
    logger.error("VoiceLive connection failure: %s", exc)
```

`ServerEventError` carries a structured `error` payload; log `error.type` and `error.code`
and surface a spoken fallback rather than silence.

## Removed / renamed API cheat sheet

| Old | New |
|---|---|
| sync `azure.ai.voicelive.connect` | `azure.ai.voicelive.aio.connect` (async-only) |
| `EOUDetection`, `AzureSemanticEOUDetection` | `EouDetection`, `AzureSemanticDetection*` |
| `AzureMultilingualSemanticVad` | `AzureSemanticVadMultilingual` |
| `OAIVoice` | `OpenAIVoiceName` |
| `ToolChoiceObject` | `ToolChoiceFunctionObject` |
| `Usage` | `TokenUsage` |
| `"pcm16-16000hz"` | `"pcm16_16000hz"` |
| semantic detection `threshold`/`timeout` | `threshold_level`/`timeout_ms` |
