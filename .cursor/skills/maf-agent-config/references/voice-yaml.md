# Voice YAML — Field Map and SDK Mapping

Maps 1:1 onto `RequestSession` from `azure.ai.voicelive.models`. Keys are snake_case;
enum-ish values are lowercase strings mapped by the loader. Unknown keys are a startup error.

## Top level

| Key | Type | Required | Notes |
|---|---|---|---|
| `extends` | str | no | Relative path to a fragment, e.g. `_base.voice.yaml` |
| `topology` | enum | yes | `maf_bridge` |
| `agent` | str | conditional | Agent config stem. Required for `maf_bridge` |
| `connection` | mapping | no | Transport tuning only; endpoint/model inherit from settings |
| `session` | mapping | yes | Everything that becomes `RequestSession` |
| `resilience` | mapping | no | Reconnect behaviour |

## Topology constraints (enforced by the loader)

| `topology` | Requires | Forbids |
|---|---|---|
| `maf_bridge` | `agent`, `session.interim_response` | `foundry_agent` |

`maf_bridge` requires `interim_response` because the caller would otherwise sit in silence
while the local MAF agent runs.

## `connection`

| Key | Maps to | Notes |
|---|---|---|
| `receive_timeout` | `connect(receive_timeout=)` | seconds |
| `close_timeout` | `connect(close_timeout=)` | seconds |
| `handshake_timeout` | `connect(handshake_timeout=)` | seconds |
| `compression` | `connect(compression=)` | bool or zlib window int |

Endpoint, credential, and model are never required in YAML. The connection factory defaults to
the resource endpoint derived from `settings.foundry_project_endpoint`, wraps
`settings.foundry_api_key` in `AzureKeyCredential`, and uses `settings.foundry_model`.
Optional `AZURE_VOICELIVE_*` settings override those values only for a different deployment.

## `session`

### `modalities`

```yaml
modalities: [text, audio]     # -> [Modality.TEXT, Modality.AUDIO]
```

`[text]` for text-only smoke tests — useful for CI where no audio device exists.

### `voice`

```yaml
voice:
  type: azure_standard        # azure_standard | azure_custom | azure_personal | openai
  name: en-US-AvaNeural
```

| `type` | Builds | Extra keys |
|---|---|---|
| `azure_standard` | `AzureStandardVoice(name=..., type="azure-standard")` | `name` |
| `azure_custom` | `AzureCustomVoice` | `name`, `endpoint_id` |
| `azure_personal` | `AzurePersonalVoice` | `name`, `custom_lexicon_url`, `prefer_locales`, `locale`, `style`, `pitch`, `rate`, `volume` |
| `openai` | plain string passed as `voice=` | `name`: `alloy`, `echo`, `fable`, `onyx`, `nova`, `shimmer`, `marin`, `cedar` |

Native-audio models cannot use Azure custom voices. Custom and personal voice are
limited-access — confirm eligibility before a profile depends on one.

### `audio`

```yaml
audio:
  input_format: pcm16          # pcm16 | g711_ulaw | g711_alaw
  output_format: pcm16         # spellings owned by voicelive-realtime
  echo_cancellation: true
  noise_reduction: true
  transcription:
    model: whisper-1
```

| YAML | `RequestSession` field |
|---|---|
| `input_format` | `input_audio_format` (`InputAudioFormat`) |
| `output_format` | `output_audio_format` (`OutputAudioFormat`) |
| `echo_cancellation: true` | `input_audio_echo_cancellation=AudioEchoCancellation()` |
| `noise_reduction: true` | `input_audio_noise_reduction=AudioNoiseReduction()` |
| `transcription.model` | `input_audio_transcription=AudioInputTranscriptionOptions(model=...)` |

Audio format spellings are owned by `voicelive-realtime` — the loader validates YAML values
against that enum list and rejects anything else with a pointer to this table.

`echo_cancellation` must be `true` whenever capture and playback share a device, or the
agent interrupts itself.

### `turn_detection`

```yaml
turn_detection:
  type: server_vad
  threshold: 0.5
  prefix_padding_ms: 300
  silence_duration_ms: 500
```

| `type` | Builds |
|---|---|
| `server_vad` | `ServerVad` |
| `azure_semantic_vad` | `AzureSemanticVad` |
| `azure_semantic_vad_en` | `AzureSemanticVadEn` |
| `azure_semantic_vad_multilingual` | `AzureSemanticVadMultilingual` |
| `~` (explicit null) | `turn_detection=None` — client-driven turn taking |

Semantic end-of-utterance detection nests under the VAD:

```yaml
turn_detection:
  type: azure_semantic_vad
  threshold: 0.5
  prefix_padding_ms: 300
  silence_duration_ms: 500
  end_of_utterance:
    type: azure_semantic_detection_en   # ..._en | ..._multilingual
    threshold_level: default            # -> EouThresholdLevel
    timeout_ms: 2000
```

Note the field names: end-of-utterance detection takes `threshold_level`/`timeout_ms`. The
outer VAD takes `threshold`. These are different fields on different objects and are the
most common copy-paste error in hand-written session code — which is one reason it belongs
in schema-validated YAML.

Writing `turn_detection: ~` sends an explicit `null`, which is meaningful. Omitting the key
inherits from `extends` instead. Do not use omission to mean "disabled".

### `tools` and `tool_choice`

Only for `topology: maf_bridge`, and normally exactly one bridge tool:

```yaml
tools:
  - type: function
    name: ask_agent
    description: Answer any caller question using the concierge agent.
    parameters:
      type: object
      properties:
        question:
          type: string
          description: The caller's question, verbatim.
      required: [question]
tool_choice: auto            # auto | none | required
```

| `type` | Builds |
|---|---|
| `function` | `FunctionTool` |

The schema accepts only `function`; direct remote-tool connections would add another runtime
service and bypass the local MAF bridge.

Tool *results* must be serialized as a JSON string into `FunctionCallOutputItem`; that is
loop code, not config. See [voicelive-realtime](../../voicelive-realtime/SKILL.md).

### `interim_response`

```yaml
interim_response:
  type: static                 # static | llm
  triggers: [tool, latency]    # -> InterimResponseTrigger
  texts:
    - "Let me check that for you."
    - "One moment."
```

`type: llm` builds `LlmInterimResponseConfig` — context-aware filler at the cost of an extra
model call. Prefer `static` for high-volume telephony.

### `limits`

| Key | `RequestSession` field |
|---|---|
| `max_response_output_tokens` | same (`int` or `"inf"`) |
| `temperature` | same |
| `reasoning_effort` | same (`ReasoningEffort`) |

### `avatar` and `animation`

```yaml
avatar:
  avatar_type: video_avatar     # video_avatar | photo_avatar  (field is avatar_type, not type)
  character: lisa
  style: casual-sitting
  protocol: webrtc              # webrtc | websocket
  scene:
    zoom: 1.0
```

The SDK field is `avatar_type`; `type` was renamed to avoid shadowing the builtin. The YAML
key mirrors the SDK to keep the mapping obvious.

### `metadata`

```yaml
metadata:
  app: maf-voice-seed
  profile: telephony
```

Flat `dict[str, str]`. Use it to correlate VoiceLive turns with your own request ids.

## `resilience`

```yaml
resilience:
  reconnect:
    max_attempts: 5
    initial_backoff_ms: 250
    max_backoff_ms: 5000
    resume_conversation: true     # reconnect with conversation_id rather than starting fresh
```

Reconnect logic is code, but its budget is behaviour — keep it in config so a telephony
profile can be tuned without a deploy.

## Complete telephony profile

```yaml
# yaml-language-server: $schema=../schemas/voice.schema.json
extends: _base.voice.yaml

topology: maf_bridge
agent: concierge

connection:
  receive_timeout: 30

session:
  modalities: [text, audio]

  voice:
    type: azure_standard
    name: en-US-AvaNeural

  audio:
    input_format: g711_ulaw
    output_format: g711_ulaw
    echo_cancellation: true
    noise_reduction: true
    transcription:
      model: whisper-1

  turn_detection:
    type: server_vad
    threshold: 0.6
    prefix_padding_ms: 200
    silence_duration_ms: 400

  tools:
    - type: function
      name: ask_agent
      description: Answer any caller question using the concierge agent.
      parameters:
        type: object
        properties:
          question:
            type: string
            description: The caller's question, verbatim.
        required: [question]
  tool_choice: auto

  interim_response:
    type: static
    triggers: [tool]
    texts: ["One moment."]

  limits:
    max_response_output_tokens: 400
    temperature: 0.6
    reasoning_effort: low

  metadata:
    profile: telephony

resilience:
  reconnect:
    max_attempts: 5
    initial_backoff_ms: 250
    max_backoff_ms: 5000
    resume_conversation: true
```

Do not resample G.711 client-side; let the service negotiate format.

With server VAD enabled, never call `input_audio_buffer.commit()` — the service commits on
speech-stop and an extra commit raises empty-buffer errors.
