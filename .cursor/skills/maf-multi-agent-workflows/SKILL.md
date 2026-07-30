---
name: maf-multi-agent-workflows
description: "Splitting one agent into several and orchestrating them: declarative `kind: Workflow` documents that reference agent files, code-first orchestration builders, executors, and choosing between agent-as-tool, sequential, concurrent, handoff, group chat, magentic, and a graph WorkflowBuilder. Load when a second agent appears or for work under src/workflows. NOT for building a single agent, its tools, or its retrieval - load maf-foundry-agent for that."
license: MIT
compatibility: Python 3.10+; agent-framework 1.12.x (`agent_framework.orchestrations`, `WorkflowBuilder`) + agent-framework-declarative 1.0.0 (`WorkflowFactory`) + agent-framework-foundry.
metadata:
  author: MAFVoiceSeed
  version: "2.0.0"
  last-reviewed: "2026-07-29"
  verified-against: "agent-framework 1.12.1 and agent-framework-declarative 1.0.0 introspected in this repo's .venv (_workflows/_factory.py, _executors_*.py); Learn /agent-framework/workflows/declarative, 2026-07"
---

# Multi-Agent Structure & Workflow Orchestration

Single-agent construction — clients, `@tool`, skills, sessions, middleware, retrieval — is
owned by [maf-foundry-agent](../maf-foundry-agent/SKILL.md). The agent document schema is owned
by [maf-agent-config](../maf-agent-config/SKILL.md). This skill starts at the second agent.

| Task | Reference |
|---|---|
| Pick and wire one of the five built-in orchestrations | [references/orchestration-patterns.md](references/orchestration-patterns.md) |
| Hand-build a graph: executors, edges, events, checkpoints, HITL | [references/graph-workflows.md](references/graph-workflows.md) |

## First, do not split

Every added participant is another model round trip. Behind a live call that is dead air, and
the caller hears it. Split only when one of these is true:

- Two instruction sets genuinely contradict each other (a refund policy and a sales pitch).
- The tool surface has grown past reliable selection — roughly ten tools in one list.
- A step must run *without* the caller's conversation in context (summarise, classify, redact).
- A stage needs a different approval boundary or a narrower data reach than the rest.

Otherwise add a tool, not an agent. If you only need one delegated call and no shared
conversation, use `agent.as_tool(...)` and stop — that is
[maf-foundry-agent](../maf-foundry-agent/SKILL.md), not a workflow.

## Layout

Extends the canonical tree in [maf-voice-agent](../maf-voice-agent/SKILL.md); this skill owns
the multi-agent parts of it.

```text
config/
  agents/
    triage.yaml          # kind: Prompt — one flat file per participant
    refunds.yaml
    orders.yaml
  workflows/
    support.yaml         # kind: Workflow — references the agent files above
  voice/
    support.yaml         # mounts: {workflow: support} — the runnable runtime
src/<package>/
  agents/
    __init__.py          # re-exports build_*_agent factories, nothing else
    triage.py            # only when a participant needs code-only wiring
  workflows/
    __init__.py          # re-exports build_*_workflow factories
    support.py           # one module per workflow: participants in, Workflow out
    executors/
      redact.py          # non-agent nodes only
```

Participants are **flat agent documents in the shared `config/agents/` directory** — not a
directory per agent, and not a private copy per workflow. That is what the declarative workflow
schema references by relative path, and it is what lets a participant be mounted alone in DevUI
or a test. The rejected layout alternatives, with evidence, are recorded in
[maf-agent-config](../maf-agent-config/SKILL.md).

A participant document is an ordinary agent document. It never carries voice keys — those live
under `config/voice/`, and only the workflow that owns the call gets one.

Import direction is one-way and it is what keeps this testable:

`tools/ ← agents/ ← workflows/ ← voice/`

`workflows/` imports `agents/`; `agents/` must never import `workflows/`, or a participant
cannot be mounted alone in DevUI or a test. `executors/` imports neither — an executor that
needs an agent is a participant, not an executor.

## Two ways to build a workflow

Pick deliberately; they are different surfaces with different capabilities.

| | Declarative `kind: Workflow` | Code-first builders |
|---|---|---|
| Loaded by | `WorkflowFactory.create_workflow_from_yaml_path` | `agent_framework.orchestrations` / `WorkflowBuilder` |
| Expresses | A deterministic action graph: `InvokeAzureAgent`, `InvokeFunctionTool`, `InvokeMcpTool`, `SetVariable`, `ConditionGroup`, `Foreach`, `SendActivity`, `question`, `ParseValue`, `EndConversation` | The five agent orchestration patterns, and arbitrary executor graphs |
| Handoff / magentic / group chat | Not expressible — there is no `pattern:` key. Do not invent one | Yes |
| Reviewable without reading Python | Yes | No |
| Upstream stability | Declarative *workflows* are stable; declarative *agents* are experimental | Stable |

Prefer declarative when the routing is deterministic. Reach for the builders when the model
must decide who answers.

## The declarative workflow document

`agents:` maps a participant name to a **file reference**, resolved relative to the workflow
file's own directory. This is the documented mechanism: `_create_agent_from_def` calls
`AgentFactory.create_agent_from_yaml_path` for any entry carrying `file`.

```yaml
# config/workflows/support.yaml
kind: Workflow
agents:
  Triage:
    file: ../agents/triage.yaml
  Refunds:
    file: ../agents/refunds.yaml
  Orders:
    file: ../agents/orders.yaml
trigger:
  kind: OnConversationStart
  id: support
  actions:
    - kind: InvokeAzureAgent
      id: classify
      agent:
        name: Triage
    - kind: ConditionGroup
      id: route
      conditions:
        - condition: =Local.Intent = "refund"
          actions:
            - kind: InvokeAzureAgent
              id: handle_refund
              agent:
                name: Refunds
      elseActions:
        - kind: InvokeAzureAgent
          id: handle_order
          agent:
            name: Orders
```

Every action becomes a real `Executor` node in the graph. That is what makes checkpointing,
visualisation, and pause/resume work at action boundaries — and it is why each action needs a
stable `id`.

Loading it:

```python
from agent_framework.declarative import AgentFactory, WorkflowFactory

factory = WorkflowFactory(
    agent_factory=AgentFactory(
        client_kwargs={
            "credential": credential,
            "project_endpoint": settings.foundry_project_endpoint,
        },
        bindings=TOOL_BINDINGS,
        safe_mode=False,
    ),
    configuration={"FOUNDRY_MODEL": settings.foundry_model},
    restrict_env_to_configuration=True,
)
workflow = factory.create_workflow_from_yaml_path(path)
```

`configuration` plus `restrict_env_to_configuration=True` is an **allowlist** for the
environment values PowerFx expressions may read. Prefer it over opening the whole environment.

Participants that need code-only wiring — retrieval providers, middleware — are built in Python
and injected by name instead of by file. The two forms mix freely:

```python
factory = WorkflowFactory(agents={"Refunds": build_refunds_agent(client)})
```

## The factory rule extends to workflows

House rule 3 gives every agent a `build_<name>_agent(client, **deps)` factory. Workflows get
the same shape:

```python
from agent_framework import Workflow
from agent_framework.orchestrations import HandoffBuilder

from .agents import build_orders_agent, build_refunds_agent, build_triage_agent


def build_support_workflow(client, config, **deps) -> Workflow:
    triage = build_triage_agent(client, **deps)
    refunds = build_refunds_agent(client, **deps)
    orders = build_orders_agent(client, **deps)
    return (
        HandoffBuilder(
            name=config.name,
            participants=[triage, refunds, orders],
            termination_condition=config.limits.termination,
        )
        .with_start_agent(triage)
        .add_handoff(triage, [refunds, orders])
        .build()
    )
```

Two things make this correct, and both are easy to lose:

1. **Every call constructs fresh participants and executors.** Executors carry mutable state.
   Building two workflows from one builder — or from module-level participant instances —
   gives you two workflows sharing one state, and the bug shows up as a second caller seeing
   the first caller's context.
2. **Nothing is built at module scope.** Same reason as agents: network at import, and DevUI
   reload stops working.

## Mounting a workflow behind the voice bridge

The bridge topology is fixed ([maf-voice-agent](../maf-voice-agent/SKILL.md)). A workflow does
not get its own VoiceLive path — it is wrapped so the bridge tool signature never changes:

```python
workflow = build_support_workflow(client, config)
agent = workflow.as_agent(name="support")
```

`as_agent()` yields the final `AgentResponse` only, so participant chatter is never spoken.
Two consequences worth planning for:

- First-token latency is now the sum of the participants that run before the answer. The
  interim response required by the bridge topology is what covers that gap.
- With no `context_providers` passed, `as_agent()` attaches an in-memory history provider.
  That is per-process, not per-caller durable state — do not treat it as session storage.

## Wiring a code-first workflow into config

A code-first orchestration has no declarative document, so the choice of pattern and its
limits still have to be reviewable. Keep them in the workflow's own document under a
`orchestration:` key that the seed loader owns, and keep participants as file references so
both surfaces name agents the same way:

```yaml
# config/workflows/support.yaml
kind: Workflow
agents:
  Triage:   {file: ../agents/triage.yaml}
  Refunds:  {file: ../agents/refunds.yaml}
  Orders:   {file: ../agents/orders.yaml}
orchestration:                # seed-owned; only when `trigger.actions` is absent
  pattern: handoff            # sequential | concurrent | handoff | group_chat | magentic
  start: Triage               # handoff only
  limits:
    max_rounds: 8
```

A document carries either `trigger` (declarative, handed to `WorkflowFactory`) or
`orchestration` (seed-owned, handed to a builder) — never both. The loader must reject, not
default:

| Condition | Loader behaviour |
|---|---|
| Both `trigger` and `orchestration` present | raise — ambiguous which engine runs |
| `pattern` outside the enum | raise |
| An `agents` entry whose `file` does not exist | raise |
| A participant document carrying voice keys | raise — participants are not runtimes |
| `pattern: handoff` without `start` | raise |
| `pattern: group_chat` or `magentic` without a round or termination limit | raise — unbounded spend |
| Unknown key under `orchestration` | raise (`extra="forbid"`) |
| An action without a stable `id` | raise — breaks checkpoint and trace correlation |

A `magentic` manager is a participant like any other: its instructions live in its own
`config/agents/<name>.yaml`, never inline in `src/`.

## Choosing a pattern

Read down; take the first row that matches.

| The shape of the work | Use |
|---|---|
| One delegated question, no shared conversation | `agent.as_tool(...)` — not a workflow |
| Deterministic branching over agent calls, reviewable in YAML | declarative `trigger.actions` |
| Fixed pipeline, each stage refines the last | `SequentialBuilder` |
| Independent perspectives on the same input, latency-bound | `ConcurrentBuilder` |
| Route to a specialist and let the conversation continue there | `HandoffBuilder` |
| Debate or review that ends on a condition, not a fixed count | `GroupChatBuilder` |
| Open-ended; the plan is not known before the first turn | `MagenticBuilder` |
| Non-agent nodes, cycles, or explicit HITL gates | `WorkflowBuilder` |

Behind a voice call, prefer the top rows. Group chat and magentic are multi-round by
construction; run them out-of-band and speak the result, or accept that the caller waits.

Wiring for each: [references/orchestration-patterns.md](references/orchestration-patterns.md).
Hand-built graphs: [references/graph-workflows.md](references/graph-workflows.md).

## Security across participants

House rule 2 — the caller is untrusted — gets harder with several agents, because now the
*model* picks who answers.

- **Routing may change who answers, never what is reachable.** Every participant resolves its
  retrieval filter and identity from the authenticated session. A specialist with a wider
  filter is privilege escalation by conversation: the caller only has to argue their way into
  a handoff.
- **A handoff is not an authorisation.** Re-check entitlement in the tool, not at the routing
  edge.
- **Retrieved text and participant output are both untrusted.** One participant's answer
  becomes another's input; it must not be able to select tools or widen a filter.
- `approval_mode="always_require"` still holds inside a workflow. The prompt arrives as a
  `request_info` event that the host must answer — a runtime that ignores those events will
  simply hang, so wire the handler when you add the tool.

## Anti-patterns

| Pattern | Verdict |
|---|---|
| A `pattern:` key inside a declarative `trigger`/`actions` document | Declarative workflows have no orchestration patterns; use a builder |
| Both `trigger` and `orchestration` in one workflow document | Ambiguous engine; pick one |
| A participant agent inlined into the workflow document instead of `file:` | Cannot be mounted alone in DevUI or a test |
| An `agents:` `file:` path resolved from anywhere but the workflow file's directory | `base_path` is the workflow file's parent; relative paths break when loaded elsewhere |
| `from agent_framework import SequentialBuilder` / `from agent_framework.workflows import GroupChat` | Orchestration builders live in `agent_framework.orchestrations` |
| `GroupChat(...)`, `HandoffOrchestrator(...)` | Removed in the orchestrations refactor |
| `.with_orchestrator(...)`, `.with_manager(...)`, `.with_intermediate_outputs(...)`, `.register_participants(...)`, `SequentialBuilder().participants(...)` | Gone in 1.12.1; these are constructor parameters |
| `register_executor(...)`, `register_agent(...)`, `set_start_executor(...)`, or a string name in `add_edge` | Removed; pass instances and `WorkflowBuilder(start_executor=...)` |
| `WorkflowOutputEvent`, `RequestInfoEvent`, `WorkflowStatusEvent` and the other event subclasses | One `WorkflowEvent`; discriminate on `event.type` |
| `workflow.run_stream(...)` / `run_stream_from_checkpoint(...)` | `workflow.run(..., stream=True)`, resume with `run(checkpoint_id=...)` |
| Executor returning a value instead of `await ctx.yield_output(...)` | A return value is not a workflow output |
| Participants or executors built at module scope, or one builder reused across `build()` calls | Shared mutable state across callers |
| A participant agent document carrying voice keys | Two runtimes claiming one call |
| `CosmosCheckpointStorage` or any external checkpoint store | Third Azure resource; house rule 5 |
| A workflow given its own VoiceLive connection | Only one bridge; wrap with `as_agent()` |
