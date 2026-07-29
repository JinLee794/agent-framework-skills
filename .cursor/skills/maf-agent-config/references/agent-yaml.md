# Agent YAML — Field Map

Every key below is validated. Unknown keys are a startup error (`extra="forbid"`).

## Top level

| Key | Type | Required | Notes |
|---|---|---|---|
| `name` | str | yes | Must equal the file stem. Used as the agent id and the `invoke_agent` span name |
| `description` | str | yes | One line. Also becomes the description when the agent is used `as_tool` |
| `extends` | str | no | Relative path to a fragment, e.g. `_base.agent.yaml` |
| `model` | mapping | yes | See below |
| `instructions` | str (block) | yes | Use `\|` block scalar. This is the system prompt |
| `tools` | list | no | See below |
| `context_providers` | list | no | See below |
| `skills` | mapping | no | Runtime Agent Skills |
| `session` | mapping | no | Conversation/store behaviour |
| `middleware` | list[str] | no | Registry refs, applied outside-in in listed order |

## `model`

| Key | Type | Default | Notes |
|---|---|---|---|
| `deployment` | str | — | Foundry model deployment name. Almost always `${FOUNDRY_MODEL}` |
| `temperature` | float | `0.3` | Keep low for task-oriented agents |
| `top_p` | float | — | Set one of `temperature` / `top_p`, not both |
| `max_output_tokens` | int | — | Cap runaway responses. For voice, 300–600 |
| `reasoning_effort` | enum | — | `minimal` \| `low` \| `medium` \| `high`. Voice: `minimal`/`low` |

Do not put endpoints or API keys here — those are `settings`, not behaviour.

## `tools`

Two entry shapes, discriminated by which key is present.

### `ref` — a local `@tool` function

```yaml
- ref: booking.cancel_booking
  approval: always_require
  enabled: true
```

| Key | Required | Notes |
|---|---|---|
| `ref` | yes | `<module>.<function>` relative to `src/<package>/tools/` |
| `approval` | **yes** | `always_require` \| `never_require`. No default — omission raises |
| `enabled` | no | Defaults `true`. Use with an overlay to disable a tool per environment |

The loader resolves `ref` through an explicit registry, never `importlib` on arbitrary
strings from config. See the Loading section of [the parent SKILL.md](../SKILL.md).

### `agent` — another agent exposed as a tool

```yaml
- agent: researcher
  as: research
  arg_name: query
  arg_description: What to research
```

Loader builds the referenced agent from `config/agents/researcher.agent.yaml` and calls
`.as_tool(...)`. Cycles are a startup error.

## `context_providers`

Constructed in listed order; they run in that order per turn.

```yaml
context_providers:
  - type: azure_ai_search
    source_id: product_docs
    endpoint: ${AZURE_SEARCH_ENDPOINT}
    index_name: ${AZURE_SEARCH_INDEX_NAME}
    mode: semantic
    top_k: 3
    semantic_configuration_name: default
    filter: "{{ runtime.security_filter }}"
```

| `type` | Builds | Notes |
|---|---|---|
| `azure_ai_search` | `AzureAISearchContextProvider` | Loader injects the Search key and same-resource embedding function, and owns the async lifetime |
| `custom` | your `ContextProvider` | `ref:` into a registry, same as tools |

Providers that own SDK clients must be entered and closed by the loader's lifecycle, not
by the agent module. Leaking `AzureAISearchContextProvider` leaks connections.

`filter` on `azure_ai_search` is security trimming and must be a `{{ runtime.* }}` value
derived from the authenticated identity — never a literal, never user input.

## `skills`

```yaml
skills:
  paths: ["skills/"]              # runtime skill roots, repo-relative
  auto_approve_read_only: true    # load_skill + read_skill_resource; still gates run_skill_script
```

Never point `paths` at `.cursor/skills/` — those are build-time skills for the coding agent.

## `session`

```yaml
session:
  store: false         # no project-backed service persistence
  history: memory      # memory | file
```

`history: memory` is the runtime default. `history: file` is for local development and
replayable fixtures; neither adds an Azure resource.

## `middleware`

```yaml
middleware:
  - guards.require_tenant
  - guards.rate_limit
```

Registry refs, same resolution as tools. Order is outside-in: the first entry is the
outermost wrapper.

## Complete example

```yaml
# yaml-language-server: $schema=../schemas/agent.schema.json
name: concierge
description: Phone concierge that looks up and cancels bookings.
extends: _base.agent.yaml

model:
  deployment: ${FOUNDRY_MODEL}
  temperature: 0.3
  max_output_tokens: 500
  reasoning_effort: low

instructions: |
  You are a concise phone concierge for Contoso Travel.
  Always read the booking code back before making a change.
  Answer only from retrieved policy documents; if the answer is not there,
  say you do not know and offer to transfer to an agent.

tools:
  - ref: booking.get_booking
    approval: never_require
  - ref: booking.cancel_booking
    approval: always_require

context_providers:
  - type: azure_ai_search
    source_id: policy_docs
    endpoint: ${AZURE_SEARCH_ENDPOINT}
    index_name: ${AZURE_SEARCH_INDEX_NAME}
    mode: semantic
    top_k: 3
    semantic_configuration_name: content-semantic
    vector_field_name: content_vector
    filter: "{{ runtime.security_filter }}"

skills:
  paths: ["skills/"]
  auto_approve_read_only: true

session:
  store: false
  history: memory

middleware:
  - guards.require_tenant
```
