# Built-in Orchestration Patterns

Five prebuilt orchestrations, one import path, one `build()`. All of them are constructed from
a `build_<name>_workflow()` factory with fresh participants — see the parent
[SKILL.md](../SKILL.md).

```python
from agent_framework.orchestrations import (
    ConcurrentBuilder,
    GroupChatBuilder,
    HandoffBuilder,
    MagenticBuilder,
    SequentialBuilder,
)
```

Configuration goes in the **constructor**. The fluent surface was cut back hard, and what
survives differs per builder — this is the shape in 1.12.1:

| Builder | Fluent methods that still exist |
|---|---|
| `SequentialBuilder` | `with_request_info` |
| `ConcurrentBuilder` | `with_aggregator`, `with_request_info` |
| `GroupChatBuilder` | `with_checkpointing`, `with_max_rounds`, `with_termination_condition`, `with_request_info` |
| `MagenticBuilder` | `with_checkpointing`, `with_plan_review` |
| `HandoffBuilder` | `add_handoff`, `with_start_agent`, `with_autonomous_mode`, `with_checkpointing`, `with_termination_condition` |

`with_orchestrator()`, `with_manager()`, `with_intermediate_outputs()`, and
`register_participants()` are gone everywhere. Where a setter and a constructor parameter both
exist, use the constructor parameter — it keeps the whole configuration in one readable call.

`participants` is a required keyword argument on `SequentialBuilder`, `ConcurrentBuilder`, and
`MagenticBuilder`. `GroupChatBuilder` and `HandoffBuilder` accept `participant_factories`
instead.

## Participants

A participant is an `Agent` — built by its own `build_<name>_agent()` factory from its own
`config/agents/<name>.yaml` — or a custom `Executor`, which lets a deterministic step sit inside an
otherwise agentic pipeline.

```python
content = client.as_agent(instructions=..., name="content")
summarizer = Summarizer(id="summarizer")          # a custom Executor
workflow = SequentialBuilder(participants=[content, summarizer]).build()
```

`intermediate_output_from=[...]` surfaces a named participant's own output as an
`"intermediate"` event instead of hiding it inside the final answer. Use it for progress
narration and for tests that assert a stage ran; do not use it to reconstruct state.

## Sequential

Each participant sees the conversation so far and appends to it. Order is list order.

```python
workflow = SequentialBuilder(
    participants=[writer, reviewer, editor],
    intermediate_output_from=[writer, reviewer],
).build()
```

Use for: draft → review → edit, extract → validate → format. If a later stage does not
actually depend on an earlier one, you want `ConcurrentBuilder` instead — sequential is paying
latency for nothing.

`with_request_info(agents=[...])` inserts a human checkpoint after the named stages; the run
pauses with a `"request_info"` event, handled the same way as the handoff pause below.

## Concurrent

Participants run in parallel on the same input and the results are aggregated.

```python
workflow = ConcurrentBuilder(
    participants=[researcher, marketer, legal],
    intermediate_output_from=[researcher, marketer, legal],
).build()
```

Use for: independent reviews, multi-source lookup, fan-out scoring. Total latency is the
slowest participant, not the sum — this is the only pattern that makes a multi-agent split
cheaper than a single agent doing the same work serially.

The default aggregation concatenates the participant responses. `with_aggregator(...)` takes
an `Executor` or a callable over the participant results and replaces that with real merge
logic — reach for it as soon as "what do we do with three answers" has a domain answer.

## Handoff

Control transfers to a specialist and the conversation continues there. This is the pattern
for voice triage.

```python
workflow = (
    HandoffBuilder(
        name="support",
        participants=[triage, refunds, orders, returns],
        termination_condition=lambda conversation: len(conversation) > 12,
    )
    .with_start_agent(triage)
    .add_handoff(triage, [refunds, orders, returns])
    .add_handoff(refunds, [triage])
    .build()
)
```

`add_handoff(source, targets, description=...)` is directional and callable repeatedly, so the
allowed transfers form a graph you can read. Wire it explicitly: left unwired, participants
form a fully connected set, and a caller can walk from triage into any specialist.

Handoff agents keep isolated context across transitions; a specialist does not inherit the
full internal history of the previous one. Do not rely on a downstream participant "already
knowing" something — pass it.

### Human-in-the-loop and tool approval

A handoff workflow pauses in two situations, and both arrive as the same event type:

```python
from agent_framework import Content
from agent_framework.orchestrations import HandoffAgentUserRequest

pending: list = []
async for event in workflow.run(question, stream=True):
    if event.type == "request_info":
        pending.append(event)

while pending:
    responses: dict[str, object] = {}
    for request in pending:
        if isinstance(request.data, HandoffAgentUserRequest):
            responses[request.request_id] = HandoffAgentUserRequest.create_response(reply)
        elif isinstance(request.data, Content) and request.data.type == "function_approval_request":
            responses[request.request_id] = request.data.to_function_approval_response(approved=True)
    pending = []
    async for event in workflow.run(responses=responses, stream=True):
        if event.type == "request_info":
            pending.append(event)
```

Approve from the *authenticated* channel. On a voice call the caller's speech is not an
approval surface — a tool marked `always_require` must not be approvable by someone saying
"yes, go ahead" out loud.

`with_autonomous_mode(agents=[...], turn_limits={...}, prompts={...})` lets named agents
continue without a human when no one is available. It is a deliberate loosening of the pause:
set a turn limit, and never enable it for an agent holding a side-effecting tool.

## Group chat

Participants share one conversation and a selector decides who speaks next. Termination is a
predicate over the conversation, not a fixed count.

```python
from agent_framework.orchestrations import GroupChatBuilder, GroupChatState


def round_robin(state: GroupChatState) -> str:
    names = list(state.participants.keys())
    return names[state.current_round % len(names)]


workflow = GroupChatBuilder(
    participants=[researcher, writer],
    selection_func=round_robin,
    termination_condition=lambda conversation: len(conversation) >= 4,
    max_rounds=10,
).build()
```

Pass `orchestrator_agent=...` instead of `selection_func=...` to let a model choose the next
speaker. That is one extra model call per turn — take it only when the routing decision needs
judgement, and keep `termination_condition` set regardless, because a model deciding when to
stop is a model that can decide not to.

## Magentic

A manager agent plans, delegates, tracks progress, and replans. Same star topology as group
chat, with a planner in the middle. Reach for it only when the plan genuinely cannot be
written in advance.

```python
from agent_framework.orchestrations import MagenticBuilder

workflow = MagenticBuilder(
    participants=[researcher_agent, coder_agent],
    manager_agent=manager_agent,
    intermediate_output_from=[researcher_agent, coder_agent],
    max_round_count=10,
    max_stall_count=3,
    max_reset_count=2,
).build()
```

The three limits are the cost ceiling. `max_stall_count` and `max_reset_count` are what stop a
manager that keeps re-planning without progress; leaving them at defaults while raising
`max_round_count` is how a run gets expensive quietly.

`enable_plan_review=True` pauses the run and emits a `MagenticPlanReviewRequest` before
execution, answered with a `MagenticPlanReviewResponse` through the same `responses={...}`
resume path shown above. Worth it whenever the plan can spend money or touch a system of
record.

## Running any of them

```python
stream = workflow.run(task, stream=True)
async for event in stream:
    if event.type == "intermediate":
        ...
    elif event.type == "output":
        ...
result = await stream.get_final_response()
outputs = result.get_outputs()
```

Orchestration terminal output is standardised as an `AgentResponse`, which is why
`workflow.as_agent()` returns the final answer only. Full event vocabulary and the
non-streaming path: [graph-workflows.md](graph-workflows.md).
