# Observability — Reference

Setup patterns and the sensitive-data rules are in the parent [SKILL.md](../SKILL.md). This
file holds the attribute/metric catalogue, correlation technique, local dashboard, and
troubleshooting.

## What Agent Framework emits

| Span | Emitted by |
|---|---|
| `invoke_agent <name>` | each `agent.run()` |
| `chat <model>` | each model call |
| `execute_tool <function>` | each tool invocation |

| Metric | Meaning |
|---|---|
| `gen_ai.client.operation.duration` | model call latency |
| `gen_ai.client.token.usage` | prompt/completion tokens |
| `agent_framework.function.invocation.duration` | tool latency |

## VoiceLive tracing

A separate instrumentor shipped in the VoiceLive SDK, opt-in behind an experimental flag:

```python
os.environ["AZURE_EXPERIMENTAL_ENABLE_GENAI_TRACING"] = "true"   # set BEFORE instrument()
from azure.ai.voicelive.telemetry import VoiceLiveInstrumentor
VoiceLiveInstrumentor().instrument()
```

It reuses the tracer provider registered by DevUI or the local console exporter. Spans cover
connect, send, and receive.

| Attribute | Meaning |
|---|---|
| `gen_ai.voice.session_id` | VoiceLive session identifier |
| `gen_ai.voice.first_token_latency_ms` | Time to first audio/text token — the key UX metric |
| `gen_ai.voice.turn_count` | Turns in the session |
| `gen_ai.voice.interruption_count` | Barge-in events; a spike means VAD is mistuned |
| `gen_ai.voice.audio_bytes_sent` / `..._received` | Audio volume |
| `gen_ai.voice.message_size` | Voice payload size |
| `gen_ai.agent.*`, `gen_ai.response.*` | Correlation with agent/response IDs |

Alert on `gen_ai.voice.first_token_latency_ms` and
`agent_framework.function.invocation.duration` — slow tools are the usual cause of dead air.

## Correlating voice and agent traces

The agent run happens inside the VoiceLive tool handler. Keep it in the active trace and stamp
the voice session ID:

```python
from agent_framework.observability import get_tracer

tracer = get_tracer()
with tracer.start_as_current_span("voice.tool.dispatch") as span:
    span.set_attribute("gen_ai.voice.session_id", session_id)
    result = await agent.run(user_text, session=agent_session)
```

Do not create a fresh root span per turn — that fragments the conversation into unlinkable
traces.

## Local development

Use DevUI's instrumentation flag for its trace panel, or a console exporter for stdout. Keep
these settings in the developer shell, not `.env.example`. This seed does not deploy a trace
collector or cloud monitoring resource.

## Troubleshooting

| Symptom | Cause |
|---|---|
| No spans at all | No provider/exporter configured — call `configure_otel_providers(...)` or launch DevUI with its tracing flag. Instrumentation itself is on by default |
| No spans after calling `disable_instrumentation()` | The disable is sticky; re-enable with `enable_instrumentation(force=True)` |
| Every span duplicated | more than one configuration pattern applied |
| Every span duplicated N times under DevUI | a telemetry initializer runs at entity import |
| Agent spans present, voice spans missing | `AZURE_EXPERIMENTAL_ENABLE_GENAI_TRACING` not set before `instrument()` |
| Voice and agent spans in separate traces | new root span created per turn in the tool bridge |
| Prompts missing from spans | `ENABLE_SENSITIVE_DATA` off (expected in production) |
| Export attempt fails | a cloud or remote exporter was configured outside this seed's contract |

If there are no spans *and* no log lines, this is not a telemetry problem — start at
[diagnostics.md](diagnostics.md).
