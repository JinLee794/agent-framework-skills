# Diagnosing a Silent Agent

Load this when the agent produces no answer, an empty answer, or an answer that ignores its
tools or its documents — and the logs do not say why.

Setup and the sensitive-data rules are in the parent [SKILL.md](../SKILL.md). Span and metric
catalogues are in [observability.md](observability.md).

## Rule zero: a run with no logs is not a data point

If a failure cannot be attributed from a log line, fix the logging first. Every claim below
assumes `setup_logging()` ran at the entry point before anything else.

## The five-minute triage

Run in order. Each step is cheap and eliminates a whole class of cause.

| # | Check | Command / signal | If it fails |
|---|---|---|---|
| 1 | Did config even load? | Look for the per-document INFO lines: path, stem, profile | Loader ran lazily or crashed silently — move validation to startup |
| 2 | Is the model id real? | Log the resolved `model.id` **after** placeholder expansion | `=Env.FOUNDRY_MODEL` unresolved (see step 3), or the deployment does not exist |
| 3 | Did `=Env.` resolve? | Resolved value logged as a literal, not as `=Env....` | `AgentFactory(safe_mode=True)` is blocking environment access — the default. Pass `safe_mode=False` |
| 4 | Are the tools bound? | Log every tool name and whether `func` is set | `func=None` — the binding name in YAML has no entry in the bindings mapping |
| 5 | Did the model actually get called? | `DEBUG` on `agent_framework`, or a `chat <model>` span | No call: the bridge tool never fired, or `tool_choice` was `auto` |

## Symptom table

Read down; the first matching row is almost always it.

| Symptom | Most likely cause |
|---|---|
| Agent answers, but never calls a tool | Tool `description` is vague, or the tool is unbound and the model gave up after one no-op |
| Tool "runs" and returns nothing, no error | `FunctionTool(func=None)` — binding name missing from `AgentFactory(bindings=...)`. Nothing raises |
| Empty or truncated response | `maxOutputTokens` too low, or written as `max_output_tokens` and therefore ignored |
| Model rejects the request as soon as options are added | Newer reasoning models reject `temperature` / `topP`. Remove them |
| Instructions clearly not applied | Key misspelled or snake_cased; the declarative schema absorbs unknown keys instead of raising |
| Agent ignores retrieved documents | `context_providers` never attached — `AgentFactory` does not build them |
| `DeclarativeLoaderError: Only definitions for a PromptAgent are supported` | `kind` is not `Prompt` |
| `ProviderLookupError` | `model.provider` is not a known provider and no `client` was passed |
| Caller hears silence, then an answer | Working as designed without `interim_response`; add one |
| Caller hears nothing at all | The bridge tool never fired — check `tool_choice: required` and that the tool name matches |
| VoiceLive connects, agent never runs | The tool handler raised; the exception was swallowed by the event loop. Log and re-raise in the dispatcher |
| Works in DevUI, fails on a call | Something in the voice path, not the agent — compare the two mounted objects, they must be identical |
| Nothing in the logs at all | `setup_logging()` not called, or called after the failing import |

## Logging the four facts that matter

Everything above depends on four log lines the seed must emit. Emit them at INFO at startup,
once, and the triage table becomes mechanical.

```python
logger.info("config loaded: stem=%s path=%s profile=%s", stem, path, profile)
logger.info("agent %s: model=%s provider=%s", agent.name, model_id, provider)
logger.info("agent %s: tools=%s", agent.name, [(t.name, t.func is not None) for t in tools])
logger.info("voice %s: mounts=%s tool_choice=%s interim=%s", name, mounts, tool_choice, interim)
```

The `t.func is not None` column is the one people leave out, and it is the one that catches the
most common silent failure in the declarative path.

## Making failures loud

Three places swallow exceptions by default. Fix all three or the logs stay empty.

**The VoiceLive event dispatcher.** An exception inside a tool handler does not surface to the
caller; the session simply goes quiet.

```python
try:
    result = await agent.run(user_text, session=agent_session)
except Exception:
    logger.exception("bridge tool failed for session %s", session_id)
    result = "Sorry, I hit an error looking that up."   # always speak something
    raise
```

Return a spoken fallback *and* log the traceback. Silence is the worst possible failure mode on
a phone call.

**Background asyncio tasks.** A task whose exception is never retrieved logs only at
interpreter shutdown. Attach a done-callback that logs, or `await` it.

**Declarative loading.** `create_agent_from_yaml_path` raises `DeclarativeLoaderError` for a
bad document, but silently drops unknown keys. Only startup validation catches the second case.

## Turning up the volume

```powershell
# Framework internals: HTTP calls, tool dispatch, declarative loading
$env:LOG_LEVEL="DEBUG"

# Prompts, responses, tool arguments in spans. Local only.
$env:ENABLE_SENSITIVE_DATA="true"

# Traces and metrics to stdout without any Azure resource
$env:ENABLE_CONSOLE_EXPORTERS="true"
```

`ENABLE_SENSITIVE_DATA` and `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` record real
callers' words. Never commit either as `true`.

Useful sub-loggers when `agent_framework` at DEBUG is too noisy:

| Logger | Covers |
|---|---|
| `agent_framework` | agent runs, tool dispatch, chat clients |
| `agent_framework.declarative` | document parsing, agent/workflow construction |
| `azure.ai.voicelive` | session lifecycle and transport |
| `azure.core.pipeline.policies.http_logging_policy` | raw HTTP; the last resort |
| `<package>` | this repo's own lines |

Set `azure.identity` to `WARNING` unless you are debugging auth — it is extremely chatty and
buries everything else.

## Before you conclude "the model is wrong"

The model is rarely wrong first. In order of observed frequency in this seed:

1. A tool was declared but never bound.
2. A camelCase key was written in snake_case and silently dropped.
3. `safe_mode` left at its default, so `=Env.` never resolved.
4. The wrong document was mounted — check the stem, not the `name` field.
5. `tool_choice: auto` let the transport model answer without the bridge.
6. The deployment name in `FOUNDRY_MODEL` does not exist in the project.

Only after all six are ruled out by a log line is it worth editing the prompt.
