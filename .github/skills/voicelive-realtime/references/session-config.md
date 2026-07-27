# VoiceLive Session Configuration — Reference

## Model selection

| Model | Audio path | Notes |
|---|---|---|
| `gpt-realtime`, `gpt-realtime-1.5`, `gpt-realtime-mini` | native speech-to-speech | Lowest latency; use for interactive voice |
| `azure-realtime` | native | Azure-hosted realtime variant |
| `gpt-5.4`, `gpt-5.3-chat`, `gpt-5.2`, `gpt-5.1`, `gpt-5`, `gpt-5-mini`, `gpt-5-nano` | cascaded (Azure STT + TTS) | Enables Azure neural, custom, and personal voices |
| `gpt-4.1`, `gpt-4.1-mini`, `gpt-4.1-nano`, `gpt-4o`, `gpt-4o-mini` | cascaded | Cost-optimized cascaded options |
| `phi4-mm-realtime`, `phi4-mini` | preview | Preview only — do not use in production paths |

Cascaded models add STT and TTS hops, so budget more end-to-end latency and pair them with
an interim response. Native audio models cannot use Azure custom voices.

`reasoning_effort` (`ReasoningEffort`) is settable on the session for reasoning-capable
models. For voice, keep it low — reasoning latency is audible.

## `RequestSession` field map

| Field | Type | Guidance |
|---|---|---|
| `modalities` | `list[Modality]` | `[TEXT, AUDIO]` for speech-out; `[TEXT]` for text-only tests |
| `instructions` | `str` | Omit when using topology A (Foundry agent owns instructions) |
| `voice` | `AzureStandardVoice` \| `AzureCustomVoice` \| `AzurePersonalVoice` \| `str` | String selects an OpenAI voice |
| `input_audio_format` | `InputAudioFormat` | `PCM16`, `G711_ULAW`, `G711_ALAW` |
| `output_audio_format` | `OutputAudioFormat` | `PCM16`, `PCM16_8000HZ`, `PCM16_16000HZ`, `G711_ULAW`, `G711_ALAW` |
| `input_audio_echo_cancellation` | `AudioEchoCancellation` | Required for shared-device capture/playback |
| `input_audio_noise_reduction` | `AudioNoiseReduction` | Recommended for telephony |
| `input_audio_transcription` | `AudioInputTranscriptionOptions` | Needed if you want user transcripts |
| `turn_detection` | `ServerVad` \| `AzureSemanticVad*` \| `None` | `None` = client-driven turn taking |
| `tools` | `list[Tool]` | `FunctionTool`, `MCPTool`, web/file search |
| `tool_choice` | `ToolChoiceLiteral` \| `ToolChoiceFunctionObject` \| `ToolChoiceMCPObject` | `ToolChoiceObject` was renamed to `ToolChoiceFunctionObject` |
| `interim_response` | `StaticInterimResponseConfig` \| `LlmInterimResponseConfig` | Cover tool/model latency |
| `avatar` | `AvatarConfig` | `avatar_type`, not `type` |
| `animation` | `AnimationOptions` | Viseme/blendshape output |
| `max_response_output_tokens` | `int` \| `"inf"` | Cap runaway responses |
| `temperature` | `float` | Keep low for task-oriented voice agents |
| `reasoning_effort` | `ReasoningEffort` | Low for latency-sensitive voice |
| `metadata` | `dict[str, str]` | Correlate turns with your own request IDs |

## Telephony profile (G.711)

```python
session = RequestSession(
    modalities=[Modality.TEXT, Modality.AUDIO],
    input_audio_format=InputAudioFormat.G711_ULAW,
    output_audio_format=OutputAudioFormat.G711_ULAW,
    input_audio_noise_reduction=AudioNoiseReduction(),
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
| `connection.output_audio_buffer` | `clear` | Discard queued output on barge-in |
| `connection.response` | `create`, `cancel` | Request or abandon a response |
| `connection.conversation.item` | `create`, `delete`, `truncate`, `retrieve` | Manage conversation items |
| `connection.session` | `update`, `avatar.connect` | Session config; avatar WebRTC negotiation |

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
| `FoundryAgentTool`, `ResponseFoundryAgentCall*` | `connect(agent_name=..., project_name=...)` |
| `EOUDetection`, `AzureSemanticEOUDetection` | `EouDetection`, `AzureSemanticDetection*` |
| `AzureMultilingualSemanticVad` | `AzureSemanticVadMultilingual` |
| `OAIVoice` | `OpenAIVoiceName` |
| `ToolChoiceObject` | `ToolChoiceFunctionObject` |
| `Usage` | `TokenUsage` |
| `AvatarConfig.type` | `AvatarConfig.avatar_type` |
| `"pcm16-16000hz"` | `"pcm16_16000hz"` |
| semantic detection `threshold`/`timeout` | `threshold_level`/`timeout_ms` |
