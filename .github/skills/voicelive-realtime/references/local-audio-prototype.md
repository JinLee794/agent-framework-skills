# Local Audio Prototype - Microphone to VoiceLive to Speakers

Use this workflow to prove the local full-duplex audio channel before debugging tools,
retrieval, or the MAF bridge. The closest upstream example is Microsoft's
[Python model quickstart](https://github.com/microsoft-foundry/voicelive-samples/blob/main/python/voice-live-quickstarts/model-quickstart.py).
Adapt its audio bridge to this seed's declarative config and explicit VoiceLive-key contract;
do not copy unrelated environment variable names verbatim.

This is a development harness, not a deployment topology. The checked-in application still
uses `maf_bridge`; a direct-model smoke test exists only to isolate microphone, speaker, and
WebSocket failures.

Create the smoke entry point in the target repository at `scripts/voice_smoke.py`. This skill
intentionally does not bundle a Python template: session construction must use that
repository's current voice config loader and builder rather than a second hard-coded copy.

## Pick the failing boundary first

| Need to prove | Start with |
|---|---|
| Microphone, speaker, WebSocket, and VoiceLive session | Direct-model smoke entry point in `scripts/` |
| Agent instructions, tools, session state, or retrieval | The brain in text-only DevUI; see [maf-dev-loop](../../maf-dev-loop/SKILL.md) |
| End-to-end voice plus reasoning | The same audio bridge around the repo's `build_<name>_agent()` product |

Do not start with the upstream project-agent quickstart. The direct-model smoke test should
isolate audio transport before involving the project-backed MAF brain.

## 1. Prepare the local audio environment

Use the repository's existing dependency mechanism. The prototype needs:

```text
azure-ai-voicelive[aiohttp]>=1.2.0
pyaudio
python-dotenv
```

On Windows, `python -m pip install pyaudio` normally installs a wheel. On macOS, install
PortAudio before PyAudio. On Linux, install the distribution's PortAudio development package
before PyAudio. Keep these as development dependencies if the deployed runtime has no local
sound device.

Use this environment contract:

```dotenv
FOUNDRY_PROJECT_ENDPOINT=https://<resource>.services.ai.azure.com/api/projects/<project>
FOUNDRY_API_KEY=<Foundry resource key>
FOUNDRY_MODEL=<Voice Live-managed model ID or same-resource BYOM deployment name>

# OPTIONAL: only for VoiceLive on another Foundry resource/project.
# AZURE_VOICELIVE_ENDPOINT=https://<other-resource>.services.ai.azure.com
# AZURE_VOICELIVE_API_KEY=<other-resource-key>
# AZURE_VOICELIVE_MODEL=<other-model-or-deployment-name>
# AZURE_VOICELIVE_PROFILE=byom-azure-openai-chat-completion
```

Call `load_dotenv()` once in the process entry point. Voice, instructions, VAD, formats, and
echo cancellation remain in `config/voice/*.voice.yaml`; load them through the normal config
builder. No `AZURE_VOICELIVE_*` setting is required for the primary Foundry deployment. The
project-backed MAF brain uses Entra separately; see the
[environment contract](../../maf-voice-agent/references/env-contract.md).
Confirm the VoiceLive model source before interpreting `FOUNDRY_MODEL`; BYOM also requires a
matching `profile` query as described in [session configuration](session-config.md).

## 2. Make device selection observable

Before opening the WebSocket, create a short-lived `pyaudio.PyAudio()` instance and enumerate
every device with its index, name, host API, maximum input channels, maximum output channels,
and default sample rate. The smoke entry point should support:

```text
--list-devices
--input-device <index>
--output-device <index>
--verbose
```

Default to the operating system's current input and output devices, but pass explicit
`input_device_index` and `output_device_index` to `PyAudio.open()` when the user selects them.
Fail before connecting when no input or output device exists. Check microphone privacy access
on Windows before changing code.

The VoiceLive PCM path is signed 16-bit, 24 kHz, mono. Start with 50 ms capture chunks:

```python
sample_format = pyaudio.paInt16
channels = 1
sample_rate = 24_000
frames_per_buffer = 1_200
```

Use `is_format_supported()` for both selected devices. If hardware cannot open 24 kHz mono,
choose another device or add an explicit streaming resampler at the device boundary. Do not
silently change the VoiceLive wire format.

## 3. Keep audio callbacks off the event loop

PyAudio invokes callbacks on PortAudio threads; the VoiceLive connection belongs to the
asyncio loop. Keep that ownership boundary explicit:

1. Save `asyncio.get_running_loop()` after the VoiceLive connection opens.
2. In the input callback, Base64-encode each PCM chunk and submit
   `connection.input_audio_buffer.append(audio=...)` with
   `asyncio.run_coroutine_threadsafe()`.
3. Observe each returned future and surface send failures. An ignored future hides a closed
   connection until the playback side also fails.
4. In the VoiceLive event loop, put each `RESPONSE_AUDIO_DELTA` byte payload into a
   thread-safe playback queue.
5. In the output callback, consume exactly the requested byte count and pad underruns with
   silence. Never call blocking `stream.write()` on the asyncio loop.

Use one capture stream, one playback stream, and one playback consumer. A second consumer
causes duplicated or reordered audio.

## 4. Open the session in a deterministic order

The smoke path should perform these steps in order:

1. Load settings and the checked-in voice YAML.
2. Resolve VoiceLive settings with the parent skill's fallback and open `connect()`.
3. Build and send `RequestSession` through the normal config builder.
4. Open playback so it is ready before the first response.
5. Process server events continuously.
6. Start microphone capture only after `SESSION_UPDATED` confirms the session configuration.

With server VAD enabled, append audio continuously and do not call
`input_audio_buffer.commit()`. Do not end the event loop on `RESPONSE_DONE`; that event ends one
turn, not the conversation.

## 5. Make barge-in audible and complete

Track whether a response is active and give queued playback packets a monotonically
increasing generation. On `INPUT_AUDIO_BUFFER_SPEECH_STARTED`:

1. Advance the playback generation so the output callback immediately discards queued and
   partially staged audio from the old response.
2. Call `connection.response.cancel()` when a response is active. Treat the race where the
   response already completed as benign.
3. Call `connection.output_audio_buffer.clear()` to discard service-side output already
   buffered for playback.

Do not close and reopen the speaker stream for every interruption. Invalidate stale packets
while the stream remains open; reopening adds latency and often leaves Windows audio devices
busy.

## 6. Shut down in the opposite order

Keep cleanup in `finally` so Ctrl+C and connection failures use the same path:

1. Stop and close the input stream so no callback can submit more coroutines.
2. Cancel or await outstanding audio-send futures.
3. Invalidate queued playback, signal the output callback, then stop and close its stream.
4. Terminate the `PyAudio` instance exactly once.
5. Let the `async with connect(...)` block close the VoiceLive connection.

An `Event loop is closed` message during exit means capture outlived the loop. A device that
remains busy after exit means a stream or the PyAudio instance was not closed.

## 7. Run the shortest discriminating checks

Run in this order; each check isolates a different failure class:

1. `python scripts/voice_smoke.py --list-devices` lists at least one usable input and output.
2. Open both selected devices at 24 kHz PCM16 mono without connecting to Azure.
3. Connect with capture muted and receive `SESSION_UPDATED` without `ERROR`.
4. Speak one sentence and hear one complete response.
5. Interrupt a long response; playback stops immediately and the next response contains no
   stale audio.
6. Complete three turns; `RESPONSE_DONE` does not close the session.
7. Press Ctrl+C, rerun immediately, and confirm both devices reopen.
8. Run the repository conformance grep checklist.

Only after checks 1-7 pass should the local entry point be connected to the MAF brain. Keep
the audio bridge unchanged during that integration so a reasoning failure cannot masquerade
as an audio-device failure.

## Fast failure map

| Symptom | Cheapest check or fix |
|---|---|
| No devices listed | OS privacy settings, default device, then driver/host API |
| `Invalid sample rate` | `is_format_supported()`; select another device or resample explicitly |
| Device busy | Close Teams/Zoom, then verify every stream closes in `finally` |
| `401` / `403` | Endpoint and `FOUNDRY_API_KEY` must belong to the same Foundry resource |
| Connected but no input | Start capture after `SESSION_UPDATED`; verify 24 kHz PCM16 mono chunks |
| No turn completes | Check server VAD config and confirm no manual `commit()` is mixed in |
| Assistant interrupts itself | Use headphones first, then verify echo cancellation is enabled in YAML |
| Choppy playback | Keep blocking work off asyncio; inspect queue underruns and chunk cadence |
| Old words play after interruption | Invalidate local playback, cancel response, and clear service output |
| Works for one turn only | Remove any `break` on `RESPONSE_DONE` |
| Exit logs `Event loop is closed` | Stop capture and settle send futures before the loop exits |

## Completion contract

The prototype is done when the device choice is visible, the session survives multiple turns,
barge-in clears both local and remote audio, Ctrl+C releases all hardware, secrets remain only
in the environment, and all behavioural settings still come from `config/voice/*.voice.yaml`.