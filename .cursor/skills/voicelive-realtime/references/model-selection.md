# VoiceLive Model Selection — Reference

This file owns model-source and model-identifier facts for VoiceLive. `RequestSession` field
shape lives in [session-config.md](session-config.md); the interview that consumes this file
lives in [../SKILL.md](../SKILL.md).

## The two sources

| Source | `connect(model=)` value | `connect(query=)` | Prerequisite |
|---|---|---|---|
| Voice Live-managed | A model identifier from the pre-deployed catalogue below | Omit it | None — Voice Live owns capacity |
| Foundry-hosted (BYOM) | Exact deployment name from the Foundry portal | `{"profile": "<byom-mode>"}` | Deployment exists on the selected VoiceLive resource |

A model name alone never identifies the source. `gpt-5.4` is a valid managed identifier *and*
a plausible deployment name, so confirm the source with the user instead of inferring it.

## Voice Live-managed catalogue

Every entry is fully managed: no deployment, no capacity planning, no provisioned throughput.

### Native speech-to-speech — lowest latency

| Model | Voices | Notes |
|---|---|---|
| `gpt-realtime-1.5` | OpenAI, or Azure TTS incl. custom | Newest native realtime |
| `gpt-realtime` | OpenAI, or Azure TTS incl. custom | Pro tier default for interactive voice |
| `gpt-realtime-mini` | OpenAI, or Azure TTS incl. custom | Basic tier; cheapest native option |
| `azure-realtime` | dedicated `azure-realtime-native` voices only | Azure-hosted native variant |

### Cascaded — Azure speech to text in, Azure text to speech out

| Model | Notes |
|---|---|
| `gpt-5.4`, `gpt-5.3-chat`, `gpt-5.2`, `gpt-5.2-chat`, `gpt-5.1`, `gpt-5.1-chat`, `gpt-5` | Highest reasoning; add STT and TTS latency |
| `gpt-5-mini`, `gpt-5-nano` | Basic and lite tiers |
| `gpt-4.1`, `gpt-4.1-mini`, `gpt-4.1-nano` | Cost-optimized |
| `gpt-4o`, `gpt-4o-mini` | Cost-optimized |
| `phi4-mm-realtime`, `phi4-mini` | Preview — never select these for a production path |

Cascaded models unlock Azure neural, custom, and personal voices at the cost of two extra
hops. Pair any cascaded selection with an interim response.

### Supported but *not* pre-deployed

`gpt-5.5`, `gpt-5.4-mini`, and `gpt-5.4-nano` are tested with Voice Live but have no managed
deployment. Reaching them requires BYOM. If the user names one of these while asking for the
managed path, say so and re-ask rather than silently substituting a different model.

### Pricing tiers

Tier follows the model; it is not selectable. Pro: `gpt-realtime`, `gpt-4o`, `gpt-4.1`,
`gpt-5`, `gpt-5-chat`. Basic: `gpt-realtime-mini`, `gpt-4o-mini`, `gpt-4.1-mini`, `gpt-5-mini`.
Lite: `gpt-5-nano`, `phi4-mm-realtime`, `phi4-mini`.

Managed availability is regional. Confirm the VoiceLive resource region supports the chosen
model before committing the value.

## BYOM profiles

Select the profile matching the deployment's API surface. Passing only a deployment name does
not select BYOM — the profile is what switches the path.

| Profile | Deployment type | Status |
|---|---|---|
| `byom-azure-openai-realtime` | Azure OpenAI realtime | GA |
| `byom-azure-openai-chat-completion` | Azure OpenAI chat completion and other compatible Foundry models | GA |
| `byom-foundry-anthropic-messages` | Anthropic Claude Messages API | Preview |

Use BYOM for a fine-tuned or provisioned-throughput deployment, for a model outside the
managed catalogue, or to reuse the deployment the local MAF brain already calls. This seed
does not support `foundry-resource-override` to a third model resource: the BYOM deployment
must live on the resource that VoiceLive connects to.

## Answer-to-configuration mapping

| Confirmed answer | `.env` | Code effect |
|---|---|---|
| Managed, same identifier as the brain | leave every `AZURE_VOICELIVE_*` unset | `voice_model` falls back to `FOUNDRY_MODEL`; `voice_query` is `None` |
| Managed, different identifier | `AZURE_VOICELIVE_MODEL=<catalogue id>` | `voice_query` stays `None` |
| BYOM on the primary resource | `AZURE_VOICELIVE_PROFILE=<byom-*>`, plus `AZURE_VOICELIVE_MODEL` if the deployment name differs | `voice_query` becomes `{"profile": ...}` |
| BYOM on an alternate VoiceLive resource | additionally `AZURE_VOICELIVE_ENDPOINT` and `AZURE_VOICELIVE_API_KEY` together | endpoint/key stop deriving from `FOUNDRY_PROJECT_ENDPOINT` |

`AZURE_VOICELIVE_PROFILE` is the single switch between the two sources. Setting it on a
managed identifier produces a deployment-not-found failure at `connect()`; omitting it for a
BYOM deployment name produces an unknown-model failure. Neither is diagnosable from the audio
path, so verify it before the first run.

## Voice compatibility

Model choice constrains voice choice — see [voices.md](voices.md). `azure-realtime` is the
sharpest constraint: it accepts only its dedicated native voices, so the checked-in
`azure_standard` voice in the voice YAML must change with it.
