# Environment Variable Contract

This seed defaults to two Azure dependencies: one Microsoft Foundry resource/project and one
Azure AI Search service. Project inference and embeddings use Entra authentication; VoiceLive
and Search use API keys. An explicit optional VoiceLive override may target another existing
Foundry deployment. Do not add monitoring, storage, database, Content Understanding, or
separate model-only resources.

Environment carries deployment values only: endpoints, model and Search object names, and
credentials. Behaviour such as instructions, model tuning, tool lists, voice, VAD thresholds,
and interim phrases belongs in `config/**.yaml`. YAML may reference these names as `${VAR}`
placeholders; it never contains their values.

## Microsoft Foundry project

Use the project endpoint for chat and embeddings. `FoundryChatClient` and the project OpenAI
client require an Entra token credential. By default, VoiceLive derives the resource endpoint
from that project endpoint and reuses the Foundry key and chat model.

| Variable | Read by | Notes |
|---|---|---|
| `FOUNDRY_PROJECT_ENDPOINT` | `FoundryChatClient`, project OpenAI client | `https://<resource>.services.ai.azure.com/api/projects/<project>` |
| `FOUNDRY_API_KEY` | VoiceLive credential factory | Foundry resource key; wrap it in `AzureKeyCredential` |
| `FOUNDRY_MODEL` | `FoundryChatClient`, voice connection builder | Chat model deployment name, e.g. `gpt-5.4-mini` |
| `FOUNDRY_EMBEDDING_MODEL` | indexing and retrieval | Embedding deployment in the same Foundry project |

`FOUNDRY_API_KEY` is a resource key, not a separately scoped project-client key. Do not pass it
to `FoundryChatClient` or `AIProjectClient`; those clients accept token credentials only.

## Optional VoiceLive overrides

Do **not** set these for the normal same-resource deployment. The settings layer derives:

| VoiceLive value | Default |
|---|---|
| endpoint | Strip `/api/projects/<project>` from `FOUNDRY_PROJECT_ENDPOINT` |
| API key | `FOUNDRY_API_KEY` |
| model | `FOUNDRY_MODEL` |

Only set overrides when VoiceLive is hosted by a different Foundry resource, or when its model
deployment name differs. A different project under the same Foundry resource usually needs no
endpoint or key override.

| Optional variable | Use only when |
|---|---|
| `AZURE_VOICELIVE_ENDPOINT` | VoiceLive is on another Foundry resource |
| `AZURE_VOICELIVE_API_KEY` | That resource has a different key |
| `AZURE_VOICELIVE_MODEL` | The VoiceLive model or deployment name differs from `FOUNDRY_MODEL` |
| `AZURE_VOICELIVE_PROFILE` | BYOM is selected; set the matching `byom-*` profile. Unset selects a Voice Live-managed model |

Endpoint and key overrides must be set together. Mismatching an endpoint and key produces an
avoidable `401`. Model and profile can be overridden independently.

`AZURE_VOICELIVE_PROFILE` is the switch between the two VoiceLive model sources, so confirm it
with the user rather than inferring it from the model name — see
[voicelive-realtime](../../voicelive-realtime/SKILL.md).

## Azure AI Search resource

| Variable | Notes |
|---|---|
| `AZURE_SEARCH_ENDPOINT` | `https://<search-service>.search.windows.net` |
| `AZURE_SEARCH_API_KEY` | Pass as `api_key=` to `AzureAISearchContextProvider`, or wrap in `AzureKeyCredential` for Search SDK clients |
| `AZURE_SEARCH_INDEX_NAME` | The single index populated by the ingestion pipeline and queried at runtime |
| `AZURE_SEARCH_API_VERSION` | Pin to `2026-04-01`, or `2026-05-01-preview` only for a named preview capability |

Use a query key when the runtime only queries documents. Index creation, schema inspection,
statistics, and document writes require an admin key; inject it only into the indexing or
inspection process and never commit it.

## `.env.example` template

The repository-root `.env.example` is canonical and intentionally contains no third-resource
variables:

```bash
# Microsoft Foundry project
FOUNDRY_PROJECT_ENDPOINT=https://<foundry-resource>.services.ai.azure.com/api/projects/<project>
FOUNDRY_API_KEY=
FOUNDRY_MODEL=gpt-5.4-mini
FOUNDRY_EMBEDDING_MODEL=text-embedding-3-small

# OPTIONAL: set only when VoiceLive uses a different Foundry resource/project.
# By default, endpoint/key/model derive from the FOUNDRY_* values above.
# AZURE_VOICELIVE_ENDPOINT=https://<other-foundry-resource>.services.ai.azure.com
# AZURE_VOICELIVE_API_KEY=
# AZURE_VOICELIVE_MODEL=

# VoiceLive model source: unset for a Voice Live-managed model, or a byom-* profile to reach
# a deployment you own. FOUNDRY_MODEL above is not pre-deployed by Voice Live.
AZURE_VOICELIVE_PROFILE=byom-azure-openai-chat-completion

# Azure AI Search resource
AZURE_SEARCH_ENDPOINT=https://<search-service>.search.windows.net
AZURE_SEARCH_API_KEY=
AZURE_SEARCH_INDEX_NAME=
AZURE_SEARCH_API_VERSION=2026-04-01
```

## Loading rules

- Call `load_dotenv()` once, at the process entry point. Agent Framework does not load `.env`.
- Resolve all values in `settings.py`; pass them into client factories explicitly.
- Commit `.env.example`, never `.env` or populated keys.
- In deployed environments, inject the same variable names through the host's secret settings.
