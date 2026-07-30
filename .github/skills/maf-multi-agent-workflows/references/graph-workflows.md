# Graph Workflows

Use `WorkflowBuilder` when none of the five built-in orchestrations fits: deterministic
branching, non-agent nodes, cycles, or an explicit approval gate between two stages. If a
built-in fits, use it — a hand-built graph is more code to keep correct.

```python
from typing_extensions import Never

from agent_framework import (
    Executor,
    WorkflowBuilder,
    WorkflowContext,
    executor,
    handler,
    response_handler,
)
```

## Executors

Two forms. A class when the node holds state or needs several handlers; a decorated function
when it does not.

```python
class UpperCase(Executor):
    def __init__(self, id: str):
        super().__init__(id=id)

    @handler
    async def to_upper(self, text: str, ctx: WorkflowContext[str]) -> None:
        await ctx.send_message(text.upper())


@executor(id="reverse_text")
async def reverse_text(text: str, ctx: WorkflowContext[Never, str]) -> None:
    await ctx.yield_output(text[::-1])
```

- `WorkflowContext[TSend]` — this node forwards `TSend` to its successors.
- `WorkflowContext[TSend, TOutput]` — it also yields a workflow output. `Never` as the first
  parameter means terminal: it emits an output and forwards nothing.
- `await ctx.send_message(...)` moves data along an edge; `await ctx.yield_output(...)`
  produces a workflow output. **Returning a value does neither.** This is the single most
  common reason a graph "runs but produces nothing".
- Give every executor a stable `id=`. It is what appears in `event.executor_id`, in traces,
  and in the DevUI graph, so renaming one silently breaks whatever you were correlating on.

Routing is by message type: a handler is selected by the annotated type of its first
parameter. Two successors expecting different types is a legitimate way to branch, and a
successor whose handler cannot accept what its predecessor sends is a build-time error, not a
runtime one.

## Edges

`WorkflowBuilder` requires `start_executor` in the constructor and takes executor **instances**
— string names and the `register_executor()` / `register_agent()` factories were removed.

```python
workflow = (
    WorkflowBuilder(start_executor=classify)
    .add_edge(classify, handle_refund, condition=lambda r: r.intent == "refund")
    .add_edge(classify, handle_order, condition=lambda r: r.intent == "order")
    .build()
)
```

| Method | Shape |
|---|---|
| `add_edge(a, b, condition=...)` | one to one, optionally guarded by a predicate on the message |
| `add_chain([a, b, c])` | a linear run of edges |
| `add_fan_out_edges(a, [b, c])` | broadcast to every target, run concurrently |
| `add_fan_in_edges([a, b], c)` | join — `c` runs once its inputs have arrived |
| `add_switch_case_edge_group(...)` | mutually exclusive branches with a default |
| `add_multi_selection_edge_group(a, [b, c, d], selection_func=...)` | pick *n* of *m* targets at runtime |

Prefer a switch-case group over a stack of `condition=` edges when the branches are meant to be
exclusive: overlapping predicates silently fan out instead of choosing, and the symptom is
duplicated work rather than an error.

Cycles are allowed and are bounded by `WorkflowBuilder(max_iterations=...)`, which defaults to
`100`. That default is a backstop, not a design: a loop still needs its own termination
condition inside the body, or you have replaced an infinite loop with an expensive one that
fails at iteration 100.

Agents are graph nodes too: an `Agent` can be passed directly where an executor is expected,
which is how you mix a model step into an otherwise deterministic pipeline.

## State isolation

`WorkflowBuilder` holds the instances you gave it, so two `build()` calls on one builder
produce two workflows sharing one set of executors and their mutable state. Construct inside
the factory instead — this is the same rule as the agent factory, for the same reason.

```python
def build_intake_workflow(client, config, **deps) -> Workflow:
    classify = Classify(id="classify")           # fresh per call
    redact = Redact(id="redact")
    return WorkflowBuilder(start_executor=classify).add_edge(classify, redact).build()
```

## Events

There is one `WorkflowEvent` class. Discriminate on `event.type`; the per-event subclasses
(`WorkflowOutputEvent`, `RequestInfoEvent`, `WorkflowStatusEvent`, `ExecutorCompletedEvent`,
and the rest) no longer exist, so `isinstance` checks against them will not even import.

```python
async for event in workflow.run(user_input, stream=True):
    if event.type == "output":
        print(f"{event.executor_id}: {event.data}")
    elif event.type == "request_info":
        pending[event.request_id] = event.data
    elif event.type == "status":
        print(event.state)
```

Types you will actually branch on: `"started"`, `"status"`, `"executor_invoked"`,
`"executor_completed"`, `"executor_failed"`, `"output"`, `"intermediate"`, `"request_info"`,
`"failed"`, plus the `"superstep_*"` pair. Streaming token updates arrive as `"output"` events
carrying an `AgentResponseUpdate`.

Status events are **off by default** — pass `include_status_events=True` to `run()` or the
`"status"` branch above never fires. That is worth knowing before you debug a state machine
that appears not to transition.

`workflow.run(...)` without `stream=True` returns the completed result;
`run_stream()` and `run_stream_from_checkpoint()` were replaced by this single entry point,
which also takes `responses=` and `checkpoint_id=`.

## Human in the loop

Any executor can suspend the graph and wait for an answer:

```python
class ConfirmRefund(Executor):
    @handler
    async def ask(self, refund: Refund, ctx: WorkflowContext[Refund]) -> None:
        await ctx.request_info(RefundApproval(amount=refund.amount))

    @response_handler
    async def resume(self, approval: RefundApproval, ctx: WorkflowContext[Refund]) -> None:
        ...
```

The host sees a `"request_info"` event and resumes with
`workflow.run(responses={request_id: response}, stream=True)`. Two rules that matter more here
than anywhere else in the repo:

- **Answer from the authenticated channel.** The request id identifies the pause, not the
  approver. Bind the approver from the session — a transcript is not an approval.
- **A pause is a suspension, not a stall.** Nothing resumes a workflow that no one answers.
  Pair every `request_info` with a timeout path, or a dropped call leaves the run hanging.

## Checkpoints

```python
from agent_framework import InMemoryCheckpointStorage

storage = InMemoryCheckpointStorage()
workflow = WorkflowBuilder(start_executor=start, checkpoint_storage=storage).add_edge(...).build()

checkpoints = await storage.list_checkpoints(workflow_name=workflow.name)
async for event in workflow.run(checkpoint_id=checkpoints[-1].checkpoint_id, stream=True):
    ...
```

- Checkpointing is a constructor parameter; `.with_checkpointing(...)` was removed.
- Resume goes through `run(checkpoint_id=..., checkpoint_storage=...)`. Responses cannot be
  supplied during resume — resume first, then answer the re-emitted `request_info`.
- `InMemoryCheckpointStorage` for tests, `FileCheckpointStorage` for a local run. A database-
  backed store is a third Azure resource and is outside this seed's contract.
- Checkpoints deserialize saved state. Treat a checkpoint file as trusted input only if the
  process that wrote it is trusted; never load one that arrived over a request.
- Checkpoint storage and topology inspection behave differently under DevUI. Before wiring
  either into an entity, read [maf-dev-loop](../../maf-dev-loop/SKILL.md).

## Wrapping up as an agent

```python
support = build_support_workflow(client, config).as_agent(name="support")
```

This is how a graph reaches the voice bridge, DevUI, and tests as one object — the same role
the agent factory plays for a single agent. See the parent [SKILL.md](../SKILL.md).
