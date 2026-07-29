# Setup - Local Code to a Live Azure AI Search Index

This workflow assumes two existing resources: one Microsoft Foundry resource with an embedding
deployment and one Azure AI Search service. It provisions no storage, data source, indexer,
skillset, project connection, or additional model resource.

## 1. Install the narrow dependency set

```powershell
python -m pip install azure-search-documents openai azure-identity python-dotenv tiktoken
az login
```

Add parser packages only for formats the corpus actually contains:

| Format | Common local parser | Notes |
|---|---|---|
| `.txt`, `.md` | Python standard library | Decode explicitly; normalize line endings |
| `.json`, `.jsonl` | `json` | Map records to text and metadata deliberately; do not embed raw serialized objects by default |
| `.csv` | `csv` or `pandas` | Choose which columns form content and which remain filterable metadata |
| `.pdf` | `pypdf` or `PyMuPDF` | Preserve page numbers; OCR is a separate requirement for image-only pages |
| `.docx` | `python-docx` | Preserve headings and paragraphs |
| `.pptx` | `python-pptx` | Preserve slide number and speaker notes when relevant |
| `.xlsx` | `openpyxl` | Convert each meaningful row or table region to text; never embed empty cells wholesale |
| `.html` | `beautifulsoup4` or `trafilatura` | Remove navigation and scripts before chunking |

Parser choice does not change the indexing pipeline. Every loader returns the same record:

```python
from dataclasses import dataclass, field

@dataclass(frozen=True)
class SourceDocument:
    source_uri: str
    title: str
    text: str
    metadata: dict[str, str | int | bool] = field(default_factory=dict)
```

Use a canonical, stable `source_uri`: a repository-relative POSIX path for checked-in files,
or the application's durable source identifier for externally supplied content. Never use a
temporary download path as identity.

## 2. Set the repository-root `.env`

```dotenv
# Existing Microsoft Foundry project
FOUNDRY_PROJECT_ENDPOINT=https://<foundry-resource>.services.ai.azure.com/api/projects/<project>
FOUNDRY_MODEL=gpt-5.4-mini
FOUNDRY_EMBEDDING_MODEL=text-embedding-3-small

# Existing Azure AI Search service
AZURE_SEARCH_ENDPOINT=https://<search-service>.search.windows.net
AZURE_SEARCH_API_KEY=
AZURE_SEARCH_INDEX_NAME=<index-name>
AZURE_SEARCH_API_VERSION=2026-04-01
```

`FOUNDRY_EMBEDDING_MODEL` is the deployment name sent as `model=` to the project embeddings
API. It is intentionally separate from `FOUNDRY_MODEL`, the chat deployment.

The indexing process needs a Search admin key to create or change an index and upload data.
A read-only runtime can use a query key. Keep the same variable name in each process, but inject
only the privilege that process needs. Never commit `.env` or print either key.

## 3. Load settings once

At the process entry point:

```python
import os

from dotenv import load_dotenv

load_dotenv()

required = (
    "FOUNDRY_PROJECT_ENDPOINT",
    "FOUNDRY_EMBEDDING_MODEL",
    "AZURE_SEARCH_ENDPOINT",
    "AZURE_SEARCH_API_KEY",
    "AZURE_SEARCH_INDEX_NAME",
    "AZURE_SEARCH_API_VERSION",
)
missing = [name for name in required if not os.getenv(name)]
if missing:
    raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")
```

Fail on missing or placeholder values before making network calls. Log endpoint hostnames,
index name, API version, and deployment name only.

## 4. Build direct clients

Use API-key clients against the two resources. Do not discover Search through a Foundry
project connection.

```python
import os

from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.identity import AzureCliCredential, get_bearer_token_provider
from openai import OpenAI

search_credential = AzureKeyCredential(os.environ["AZURE_SEARCH_API_KEY"])
index_client = SearchIndexClient(
    endpoint=os.environ["AZURE_SEARCH_ENDPOINT"],
    credential=search_credential,
    api_version=os.environ["AZURE_SEARCH_API_VERSION"],
)
search_client = SearchClient(
    endpoint=os.environ["AZURE_SEARCH_ENDPOINT"],
    index_name=os.environ["AZURE_SEARCH_INDEX_NAME"],
    credential=search_credential,
    api_version=os.environ["AZURE_SEARCH_API_VERSION"],
)
embedding_client = OpenAI(
    base_url=f'{os.environ["FOUNDRY_PROJECT_ENDPOINT"].rstrip("/")}/openai/v1/',
    api_key=get_bearer_token_provider(
        AzureCliCredential(), "https://ai.azure.com/.default"
    ),
)
```

The v1 Foundry embeddings API uses the deployment name in `model=`. Probe it before defining
the vector field:

```python
probe = embedding_client.embeddings.create(
    model=os.environ["FOUNDRY_EMBEDDING_MODEL"],
    input="embedding dimension probe",
)
embedding_dimensions = len(probe.data[0].embedding)
```

Do not hardcode a dimension from the model family. `text-embedding-3` deployments can be
configured for reduced dimensions, and the live response is authoritative.

## 5. Inspect before creating

Run the bundled read-only check first:

```powershell
python .cursor/skills/foundry-iq/scripts/check_search.py
python .cursor/skills/foundry-iq/scripts/check_search.py --query "a corpus-specific question"
```

It validates `.env`, probes embeddings, reads the live index definition and statistics,
checks the vector dimension, then runs keyword, vector, and hybrid queries when the index
exists. It does not create, upload, update, or delete anything. See
[live-checks.md](live-checks.md) to interpret each result.

If the index does not exist, proceed to
[indexing-pipeline.md](indexing-pipeline.md). If it exists but its key, field types, or vector
dimensions differ from the intended schema, stop and version the index rather than deleting it
implicitly.

## Setup completion check

- Both endpoints and both deployment names came from `.env`.
- The embedding probe succeeds and reports a nonzero dimension.
- The Search service can be reached with the injected key.
- Existing index state is known before any mutation.
- Parser dependencies match real corpus formats; no cloud ingestion service was introduced.
