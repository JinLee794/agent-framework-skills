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

It reuses whatever tracer provider is already registered, so configure Azure Monitor (or your
OTLP exporter) first and voice spans go to the same backend automatically. Spans cover
connect, send, and recv.

| Attribute | Meaning |
|---|---|
| `gen_ai.voice.session_id` | VoiceLive session identifier |
| `gen_ai.voice.first_token_latency_ms` | Time to first audio/text token — the key UX metric |
| `gen_ai.voice.turn_count` | Turns in the session |
| `gen_ai.voice.interruption_count` | Barge-in events; a spike means VAD is mistuned |
| `gen_ai.voice.audio_bytes_sent` / `..._received` | Audio volume |
| `gen_ai.voice.message_size`, `gen_ai.voice.mcp.*` | Payload and MCP tool detail |
| `gen_ai.agent.*`, `gen_ai.response.*` | Correlation with agent/response IDs |

Alert on `gen_ai.voice.first_token_latency_ms` and
`agent_framework.function.invocation.duration` — slow tools are the usual cause of dead air.

## Correlating voice and agent traces

The instrumentor emits `gen_ai.agent.*` / `gen_ai.response.*` aligned with `azure-ai-projects`
tracing, so **topology A** correlates automatically when both sides export to the same backend.

For **topology B** the agent run happens inside the VoiceLive tool handler. Keep them in one
trace by running the agent under the active span and stamping the voice session ID:

```python
from agent_framework.observability import get_tracer

tracer = get_tracer()
with tracer.start_as_current_span("voice.tool.dispatch") as span:
    span.set_attribute("gen_ai.voice.session_id", session_id)
    result = await agent.run(user_text, session=agent_session)
```

Do not create a fresh root span per turn — that fragments the conversation into unlinkable
traces.

## Configuration patterns in full

```python
from agent_framework.observability import configure_otel_providers

configure_otel_providers()   # reads OTEL_* and ENABLE_* from the environment
```

```bash
ENABLE_INSTRUMENTATION=true
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
OTEL_SERVICE_NAME=maf-voice-agent
OTEL_RESOURCE_ATTRIBUTES=deployment.environment=dev
```

If something else already owns the tracer/meter providers, do not let Agent Framework create
its own — just turn on instrumentation:

```python
from azure.monitor.opentelemetry import configure_azure_monitor
from agent_framework.observability import enable_instrumentation

configure_azure_monitor(connection_string=os.environ["APPLICATIONINSIGHTS_CONNECTION_STRING"])
enable_instrumentation()
```

`use_microsoft_opentelemetry()` applies the Microsoft-tuned defaults in one call.

## Local development

Aspire Dashboard gives traces and metrics with no cloud dependency:

```powershell
docker run --rm -it -p 18888:18888 -p 4317:18889 `
  --name aspire-dashboard mcr.microsoft.com/dotnet/aspire-dashboard:latest
```

```bash
ENABLE_INSTRUMENTATION=true
ENABLE_SENSITIVE_DATA=true          # local only
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
```

Open `http://localhost:18888` with the login token printed by the container. Alternatives:
`ENABLE_CONSOLE_EXPORTERS=true` for stdout, or DevUI's instrumentation flag.

## Troubleshooting

| Symptom | Cause |
|---|---|
| No spans at all | `ENABLE_INSTRUMENTATION` not `true`, or setup ran after client construction |
| Every span duplicated | more than one configuration pattern applied |
| Every span duplicated N times under DevUI | a telemetry initializer runs at entity import |
| Agent spans present, voice spans missing | `AZURE_EXPERIMENTAL_ENABLE_GENAI_TRACING` not set before `instrument()` |
| Voice and agent spans in separate traces | new root span created per turn in the tool bridge |
| Prompts missing from spans | `ENABLE_SENSITIVE_DATA` off (expected in production) |
| `configure_azure_monitor` raises | no Application Insights resource linked to the Foundry project |
