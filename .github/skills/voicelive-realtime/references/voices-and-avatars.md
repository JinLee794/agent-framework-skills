# Voices, Avatars, and MCP Tools

Load this when choosing a voice, enabling an avatar, or letting VoiceLive call a remote MCP
server directly. The session-shape fundamentals are in the parent [SKILL.md](../SKILL.md).

## Voices

| Kind | Construct with | Notes |
|---|---|---|
| Azure neural | `AzureStandardVoice(name="en-US-AvaNeural", type="azure-standard")` | Also `en-US-JennyNeural`, `en-US-GuyNeural` |
| OpenAI | a plain string — `alloy`, `echo`, `fable`, `onyx`, `nova`, `shimmer`, `marin`, `cedar` | Enum is `OpenAIVoiceName`, renamed from `OAIVoice`. `marin`/`cedar` added in `1.2.0b2` |
| Custom / personal | `AzurePersonalVoice(...)` | Limited-access feature — confirm eligibility before designing around it |

`AzurePersonalVoice` accepts `custom_lexicon_url`, `prefer_locales`, `locale`, `style`,
`pitch`, `rate`, and `volume`. Use `custom_lexicon_url` for domain vocabulary — product names
and drug names are the usual reason a demo sounds wrong.

### Model choice constrains voice choice

| Model family | Voices available | Latency |
|---|---|---|
| Native-audio (`gpt-realtime`, `gpt-realtime-mini`, `azure-realtime`) | OpenAI voices | lowest — audio in, audio out |
| Text (`gpt-5.x`, `gpt-4.1`) | Azure neural + custom, via Azure STT/TTS | higher — extra STT and TTS hops |

Picking an Azure neural voice silently forces the text path. If you need both a branded voice
and minimum latency, that tension has no config answer — resolve it with the stakeholder
before building.

## Avatars

`AvatarConfig` renamed its `type` field to **`avatar_type`** in `1.2.0`, to stop shadowing the
builtin. Old code fails with a confusing constructor error.

| Setting | Values |
|---|---|
| `avatar_type` | `video-avatar`, `photo-avatar` (`AvatarConfigTypes`) |
| output protocol | `webrtc`, `websocket` (`AvatarOutputProtocol`) |
| framing | `Scene` — zoom, position, rotation |

Drive UI state from the events, not from your own timers:

| Event | Use for |
|---|---|
| `ServerEventSessionAvatarSwitchToSpeaking` | show the speaking state |
| `ServerEventSessionAvatarSwitchToIdle` | return to idle |
| `ServerEventResponseVideoDelta` | render frames |

Custom avatars are limited-access, same as custom voice. `webrtc` is the right default;
`websocket` only when you cannot negotiate a peer connection.

## MCP tools

VoiceLive can call remote MCP servers directly, without a round trip through your process.

Approval is controlled by `MCPApprovalType`: `never`, `always`, or per-tool. Handle the
approval-request server events by sending an approval response.

- Use `always` for anything with side effects.
- **Never auto-approve tools from a server you do not control.** A remote MCP server is
  untrusted input with a function-call channel into your session.
- Prefer this over a local function tool only when the server is already the system of record.
  A local `@tool` is easier to test and to trace.

The agent-side MCP surface — `MCPStreamableHTTPTool`, Foundry toolboxes, approval middleware —
is `maf-foundry-agent`, not this file.
