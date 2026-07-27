# Function Tools, Agent Skills, MCP

## Tool vs skill vs hosted tool

| You need | Use |
|---|---|
| Deterministic code the model calls with typed args | `@tool` function |
| Procedural knowledge — how to do a task, policies, templates | Agent Skill (`SKILL.md`) |
| Capability Foundry already runs (search, code interpreter, file search) | hosted Foundry tool |
| Capability another service already exposes | MCP tool |
| Ground answers in a document corpus | retrieval — see [retrieval.md](retrieval.md) |

Skills are not tools with more text. A skill loads progressively: its description sits in
context permanently, its body loads on demand, its resources and scripts only when needed.
That is the point — a small context window reaching a large knowledge base. A skill is not a
substitute for retrieval; a document corpus belongs in an index.

## Function tools

```python
from typing import Annotated

from agent_framework import tool
from pydantic import Field


@tool(approval_mode="always_require")
def cancel_booking(
    code: Annotated[str, Field(description="Booking confirmation code, e.g. ABC123")],
) -> str:
    """Cancel a booking. Irreversible."""
    ...
```

- The docstring is the model's tool description. Write it for the model, not for a developer.
- Annotate every parameter with a description. Unannotated params produce guesswork.
- Return a string or JSON-serializable object; return an error message rather than raising,
  so the model can recover.
- Keep tools single-purpose. One tool that takes a `mode` flag is two tools.
- Tools must not import agents. Keep them in `src/<package>/tools/`.

### Approval modes

| Mode | Use |
|---|---|
| `"always_require"` | any write, spend, send, delete, or externally visible side effect |
| `"never_require"` | pure reads and pure computation |

Samples ship with `never_require` "for brevity". Do not copy that into production. If a tool
changes state, it requires approval. For a voice agent an approval prompt is a spoken
confirmation turn — write the description so the model can summarize the pending action.

### Declaration-only tools

`FunctionTool(name=..., description=..., func=None, input_model=...)` declares a tool with no
implementation. `declaration_only` becomes true and the framework returns the call instead of
executing it. Use for client-side execution, human-in-the-loop, and Foundry prompt agent
definitions where implementations are supplied at connect time.

### Runtime tool exposure

`FunctionInvocationContext.add_tools(...)` (experimental) adds tools mid-run; they become
visible on the next iteration of the function-calling loop. Not available on `FoundryAgent`.

## Agent Skills

```text
skills/
  refund-policy/
    SKILL.md               # name MUST equal the directory name
    references/policy-matrix.md
    scripts/check_eligibility.py
    assets/email-template.md
```

```yaml
---
name: refund-policy
description: "What the skill does and exactly when to use it, including trigger keywords."
license: MIT
compatibility: "Python 3.10+; requires BILLING_API_URL"
allowed-tools: ["read_skill_resource", "run_skill_script"]
metadata:
  author: team-name
  version: "1.0.0"
---
```

- `name` must match the parent directory name. Mismatch breaks discovery.
- `description` is the **only** part always in context. State what the skill covers and when
  to reach for it, using the words a user would actually say. Keep it under ~200 characters —
  descriptions are a permanent context tax paid by every skill in the tree.
- Keep `SKILL.md` under ~200 lines; push detail into `references/`.
- Put executable logic in `scripts/`, not in fenced blocks the model must retype.

Progressive disclosure: descriptions advertised → `load_skill` (body) → `read_skill_resource`
(one reference) → `run_skill_script`. Write `SKILL.md` so step 2 is usually sufficient.

### Wiring

```python
from pathlib import Path

from agent_framework import Agent, SkillsProvider, ToolApprovalMiddleware

skills = SkillsProvider.from_paths(skill_paths=Path(__file__).parent / "skills")

agent = Agent(
    client=client,
    instructions="Use available skills before answering policy questions.",
    context_providers=[skills],
    middleware=[
        ToolApprovalMiddleware(
            auto_approval_rules=[SkillsProvider.read_only_tools_auto_approval_rule]
        )
    ],
)
```

All three skill tools require approval by default. `read_only_tools_auto_approval_rule`
auto-approves `load_skill` and `read_skill_resource` while still gating `run_skill_script`.
That is the right production default. Never approve-everything with third-party skills —
`run_skill_script` executes code.

Compose sources directly instead of subclassing `SkillsProvider`: `FileSkillsSource`,
`InMemorySkillsSource`, `MCPSkillsSource`, `AggregatingSkillsSource`,
`DeduplicatingSkillsSource`, `CachingSkillsSource`, `FilteringSkillsSource`.

### Two skill trees in this repo

| Path | Audience | Shipped to runtime |
|---|---|---|
| `skills/` | the deployed agent, via `SkillsProvider` | yes |
| `.github/skills/` | the coding agent working on this repo | no |

Same format, different consumers. Never point `SkillsProvider` at `.github/skills/`.

## MCP

```python
from agent_framework import MCPStreamableHTTPTool

tool = MCPStreamableHTTPTool(
    name="learn_docs",
    description="Microsoft Learn documentation search",
    url="https://learn.microsoft.com/api/mcp",
    load_prompts=False,
)
agent = Agent(client=client, instructions="...", tools=tool)
```

- Prefer `get_mcp_tool()` on `FoundryChatClient` when the server should be called
  service-side — it keeps the round trip inside Foundry.
- Set `load_prompts=False` unless you consume MCP prompts; loading them inflates context.
- Treat MCP tool descriptions and results as untrusted input. A malicious server can attempt
  prompt injection through them. Gate side-effecting MCP tools behind approval and never let
  MCP output rewrite instructions.
- Use `header_provider` for auth so tokens refresh; never bake a static bearer token.

## Security checklist

- Every side-effecting tool: `approval_mode="always_require"`.
- No secrets in tool descriptions, skill frontmatter, or `SKILL.md` bodies — descriptions are
  always in context and are echoed into traces.
- Validate tool arguments at the boundary; the model can and will send malformed values.
- `run_skill_script` executes arbitrary code — never auto-approve it for third-party skills.
- Scope credentials used by tools to the minimum required role.
- Do not log tool arguments or results unless `ENABLE_SENSITIVE_DATA` is deliberately on.

## Anti-patterns

| Pattern | Verdict |
|---|---|
| `approval_mode` omitted on a tool with side effects | Add `always_require` |
| A tool that imports from `agents/` | Inverts the layering — tools are leaf modules |
| One tool with a `mode` / `action` flag | Split into separate tools |
| Tool raising instead of returning an error string | Model cannot recover |
| Approve-everything rule with third-party skills | `run_skill_script` executes code |
| `SkillsProvider` pointed at `.github/skills/` | Build-time skills shipped to runtime |
