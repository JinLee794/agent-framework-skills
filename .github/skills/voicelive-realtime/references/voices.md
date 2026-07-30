# Voices

Load this when choosing a VoiceLive voice. Session-shape fundamentals are in the parent
[SKILL.md](../SKILL.md).

| Kind | Construct with | Notes |
|---|---|---|
| Azure neural | `AzureStandardVoice(name="en-US-AvaNeural", type="azure-standard")` | Also `en-US-JennyNeural`, `en-US-GuyNeural` |
| OpenAI | a plain string — see the enum below | Enum is `OpenAIVoiceName`, renamed from `OAIVoice`. `marin`/`cedar` added in `1.2.0b2` |
| `azure-realtime` native | `{"type": "azure-realtime-native", "name": "ava"}` | Only for the `azure-realtime` model; `ava` is the default if omitted |
| Custom / personal | `AzurePersonalVoice(...)` | Limited-access feature — confirm eligibility before designing around it |

The complete `OpenAIVoiceName` membership in `1.2.0` is `alloy`, `ash`, `ballad`, `coral`, `echo`,
`sage`, `shimmer`, `verse`, `marin`, `cedar`. The OpenAI *text-to-speech* names `fable`, `onyx`,
and `nova` are **not** realtime voices and are rejected on session update — do not offer them.

`AzurePersonalVoice` accepts `custom_lexicon_url`, `prefer_locales`, `locale`, `style`,
`pitch`, `rate`, and `volume`. Use `custom_lexicon_url` for domain vocabulary — product names
and drug names are the usual reason a demo sounds wrong.

## Model choice constrains voice choice

| Model family | Voices available | Latency |
|---|---|---|
| `gpt-realtime`, `gpt-realtime-1.5`, `gpt-realtime-mini` | OpenAI voices natively, or Azure neural/custom through TTS | lowest on OpenAI voices; an Azure voice adds a TTS hop |
| `azure-realtime` | dedicated `azure-realtime-native` voices only (`ava`, `andrew`, `clara`, `aarti`, `alvaro`, `antonio`, `william`, `ximena`, `xiaoxiao`, `yunxi`, and others) | lowest |
| Cascaded (`gpt-5.x`, `gpt-4.1`, `gpt-4o`) | full Azure neural, custom, and personal catalogue | higher — extra STT and TTS hops |

Model identifiers and their sources are owned by
[model-selection.md](model-selection.md). If you need both a branded voice and minimum
latency, resolve that tension with the stakeholder before building.

## Tool boundary

VoiceLive exposes only the local function bridge in this seed. Direct remote tool servers add
another runtime service and bypass the MAF agent's tool policy.