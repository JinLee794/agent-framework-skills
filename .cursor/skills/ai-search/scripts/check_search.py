"""Read-only checks for the Foundry embedding deployment and Azure AI Search index."""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import urlparse

EXPECTED_FIELDS = {
    "id",
    "parent_id",
    "title",
    "content",
    "source_uri",
    "chunk_index",
    "content_vector",
}
SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parents[4]


@dataclass(frozen=True)
class Settings:
    foundry_project_endpoint: str
    embedding_deployment: str
    search_endpoint: str
    search_api_key: str = field(repr=False)
    search_index_name: str
    search_api_version: str


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Probe the configured embedding deployment and inspect/query an existing "
            "Azure AI Search index without mutating it."
        )
    )
    parser.add_argument(
        "--query",
        help="Optional corpus-specific question for keyword, vector, and hybrid checks.",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=3,
        help="Maximum results to report for each query check (default: 3).",
    )
    args = parser.parse_args(argv)
    if args.top < 1 or args.top > 50:
        parser.error("--top must be between 1 and 50")
    return args


def load_dependencies() -> tuple[Any, ...]:
    try:
        from azure.core.credentials import AzureKeyCredential
        from azure.core.exceptions import HttpResponseError, ResourceNotFoundError
        from azure.search.documents import SearchClient
        from azure.search.documents.indexes import SearchIndexClient
        from azure.search.documents.models import VectorizedQuery
        from azure.identity import AzureCliCredential, get_bearer_token_provider
        from dotenv import load_dotenv
        from openai import APIConnectionError, APIStatusError, OpenAI
    except ModuleNotFoundError as exc:
        package = exc.name or "a required package"
        raise RuntimeError(
            f"Missing Python module '{package}'. Install azure-search-documents, "
            "openai, azure-identity, and python-dotenv."
        ) from exc

    return (
        AzureKeyCredential,
        HttpResponseError,
        ResourceNotFoundError,
        SearchClient,
        SearchIndexClient,
        VectorizedQuery,
        AzureCliCredential,
        get_bearer_token_provider,
        load_dotenv,
        APIConnectionError,
        APIStatusError,
        OpenAI,
    )


def load_settings(load_dotenv: Any) -> Settings:
    dotenv_path = REPO_ROOT / ".env"
    load_dotenv(dotenv_path=dotenv_path)

    env_names = {
        "foundry_project_endpoint": "FOUNDRY_PROJECT_ENDPOINT",
        "embedding_deployment": "FOUNDRY_EMBEDDING_MODEL",
        "search_endpoint": "AZURE_SEARCH_ENDPOINT",
        "search_api_key": "AZURE_SEARCH_API_KEY",
        "search_index_name": "AZURE_SEARCH_INDEX_NAME",
        "search_api_version": "AZURE_SEARCH_API_VERSION",
    }
    values = {field_name: os.getenv(env_name, "").strip() for field_name, env_name in env_names.items()}
    invalid = [
        env_names[field_name]
        for field_name, value in values.items()
        if not value or "<" in value or ">" in value
    ]
    if invalid:
        source = str(dotenv_path) if dotenv_path.exists() else "the process environment"
        raise RuntimeError(
            f"Missing or placeholder deployment values in {source}: {', '.join(invalid)}"
        )

    return Settings(**values)


def endpoint_host(endpoint: str) -> str:
    parsed = urlparse(endpoint)
    if parsed.scheme != "https" or not parsed.hostname:
        raise RuntimeError(f"Expected an HTTPS endpoint, got host '{parsed.hostname or 'unknown'}'")
    return parsed.hostname


def project_openai_base_url(endpoint: str) -> str:
    base = endpoint.rstrip("/")
    if "/api/projects/" not in urlparse(base).path:
        raise RuntimeError(
            "FOUNDRY_PROJECT_ENDPOINT must end with /api/projects/<project>"
        )
    if base.endswith("/openai/v1"):
        return f"{base}/"
    return f"{base}/openai/v1/"


def describe_http_error(error: Exception) -> str:
    response = getattr(error, "response", None)
    status = getattr(response, "status_code", None) or getattr(error, "status_code", None)
    reason = getattr(error, "reason", None) or type(error).__name__
    return f"status={status or 'unknown'}, reason={reason}"


def probe_embedding(client: Any, deployment: str, api_status_error: type[Exception], api_connection_error: type[Exception]) -> tuple[int, list[float]]:
    try:
        response = client.embeddings.create(
            model=deployment,
            input="Azure AI Search embedding dimension probe",
        )
    except api_status_error as exc:
        raise RuntimeError(f"Embedding probe failed ({describe_http_error(exc)})") from exc
    except api_connection_error as exc:
        raise RuntimeError("Embedding endpoint could not be reached") from exc

    if not response.data or not response.data[0].embedding:
        raise RuntimeError("Embedding probe returned no vector")
    vector = response.data[0].embedding
    return len(vector), vector


def field_summary(field_value: Any) -> str:
    attributes = [
        f"type={field_value.type}",
        f"key={bool(field_value.key)}",
        f"searchable={bool(field_value.searchable)}",
        f"filterable={bool(field_value.filterable)}",
        f"retrievable={field_value.retrievable is not False}",
    ]
    dimensions = getattr(field_value, "vector_search_dimensions", None)
    profile = getattr(field_value, "vector_search_profile_name", None)
    if dimensions is not None:
        attributes.append(f"dimensions={dimensions}")
    if profile:
        attributes.append(f"profile={profile}")
    return ", ".join(attributes)


def semantic_configurations(index: Any) -> tuple[list[str], str | None]:
    semantic_search = getattr(index, "semantic_search", None)
    if semantic_search is None:
        return [], None
    configurations = list(getattr(semantic_search, "configurations", None) or [])
    names = [configuration.name for configuration in configurations]
    matching_name = None
    for configuration in configurations:
        prioritized = getattr(configuration, "prioritized_fields", None)
        title = getattr(getattr(prioritized, "title_field", None), "field_name", None)
        content = {
            item.field_name
            for item in (getattr(prioritized, "content_fields", None) or [])
        }
        if title == "title" and "content" in content:
            matching_name = configuration.name
            break
    return names, matching_name


def inspect_schema(index: Any, embedding_dimensions: int) -> tuple[list[str], list[str], str | None]:
    errors: list[str] = []
    warnings: list[str] = []
    fields = {field_value.name: field_value for field_value in index.fields}

    print("\nSchema")
    for name in sorted(fields):
        print(f"  {name}: {field_summary(fields[name])}")

    missing = sorted(EXPECTED_FIELDS - fields.keys())
    if missing:
        errors.append(f"missing expected fields: {', '.join(missing)}")

    key_names = sorted(name for name, value in fields.items() if value.key)
    if key_names != ["id"]:
        errors.append(f"expected key field 'id'; live key fields: {key_names or ['none']}")

    for name in ("title", "content"):
        value = fields.get(name)
        if value is not None and (not value.searchable or value.retrievable is False):
            errors.append(f"field '{name}' must be searchable and retrievable")

    for name in ("parent_id", "source_uri"):
        value = fields.get(name)
        if value is not None and not value.filterable:
            errors.append(f"field '{name}' must be filterable")

    vector_field = fields.get("content_vector")
    if vector_field is not None:
        dimensions = getattr(vector_field, "vector_search_dimensions", None)
        if dimensions != embedding_dimensions:
            errors.append(
                "content_vector dimensions "
                f"({dimensions}) do not match the embedding deployment ({embedding_dimensions})"
            )
        if not vector_field.searchable:
            errors.append("field 'content_vector' must be searchable")

        profile = getattr(vector_field, "vector_search_profile_name", None)
        profiles = list(getattr(getattr(index, "vector_search", None), "profiles", None) or [])
        profile_names = {item.name for item in profiles}
        if not profile or profile not in profile_names:
            errors.append("content_vector is not attached to a defined vector profile")

    semantic_names, matching_semantic = semantic_configurations(index)
    print(f"  semantic configurations: {semantic_names or ['none']}")
    if matching_semantic is None:
        warnings.append("no semantic configuration maps title/content to the expected fields")

    return errors, warnings, matching_semantic


def result_select_fields(index: Any) -> list[str]:
    fields = {field_value.name: field_value for field_value in index.fields}
    key_names = [name for name, value in fields.items() if value.key]
    selected = key_names[:1]
    for name in ("title", "source_uri"):
        value = fields.get(name)
        if value is not None and value.retrievable is not False:
            selected.append(name)
    return selected


def report_results(label: str, results: Any, selected: Sequence[str]) -> None:
    print(f"\n{label}")
    count = 0
    for result in results:
        count += 1
        metadata = ", ".join(f"{name}={result.get(name)!r}" for name in selected)
        score = result.get("@search.score")
        reranker = result.get("@search.reranker_score")
        print(f"  {metadata}, score={score!r}, reranker_score={reranker!r}")
    if count == 0:
        print("  no results")


def run_queries(
    search_client: Any,
    vectorized_query: Any,
    embedding_client: Any,
    deployment: str,
    index: Any,
    query: str | None,
    top: int,
    semantic_name: str | None,
) -> list[str]:
    errors: list[str] = []
    selected = result_select_fields(index)
    if not selected:
        return ["no retrievable key field is available for query checks"]

    try:
        sample = search_client.search(search_text="*", select=selected, top=top)
        report_results("Sample documents", sample, selected)
    except Exception as exc:
        return [f"sample query failed ({describe_http_error(exc)})"]

    if not query:
        return errors

    try:
        keyword = search_client.search(search_text=query, select=selected, top=top)
        report_results("Keyword results", keyword, selected)

        response = embedding_client.embeddings.create(model=deployment, input=query)
        query_vector = response.data[0].embedding
        vector_query = vectorized_query(
            vector=query_vector,
            k_nearest_neighbors=top,
            fields="content_vector",
        )
        vector = search_client.search(
            search_text=None,
            vector_queries=[vector_query],
            select=selected,
            top=top,
        )
        report_results("Vector results", vector, selected)

        hybrid_options: dict[str, Any] = {}
        if semantic_name:
            hybrid_options.update(
                query_type="semantic",
                semantic_configuration_name=semantic_name,
            )
        hybrid = search_client.search(
            search_text=query,
            vector_queries=[vector_query],
            select=selected,
            top=top,
            **hybrid_options,
        )
        label = "Hybrid + semantic results" if semantic_name else "Hybrid results"
        report_results(label, hybrid, selected)
    except Exception as exc:
        errors.append(f"query checks failed ({describe_http_error(exc)})")

    return errors


def run(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        (
            AzureKeyCredential,
            HttpResponseError,
            ResourceNotFoundError,
            SearchClient,
            SearchIndexClient,
            VectorizedQuery,
            AzureCliCredential,
            get_bearer_token_provider,
            load_dotenv,
            APIConnectionError,
            APIStatusError,
            OpenAI,
        ) = load_dependencies()
        settings = load_settings(load_dotenv)
        foundry_host = endpoint_host(settings.foundry_project_endpoint)
        search_host = endpoint_host(settings.search_endpoint)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print("Configuration")
    print(f"  Foundry host: {foundry_host}")
    print(f"  Embedding deployment: {settings.embedding_deployment}")
    print(f"  Search host: {search_host}")
    print(f"  Search index: {settings.search_index_name}")
    print(f"  Search API version: {settings.search_api_version}")

    errors: list[str] = []
    warnings: list[str] = []
    foundry_credential = AzureCliCredential()
    embedding_client = OpenAI(
        base_url=project_openai_base_url(settings.foundry_project_endpoint),
        api_key=get_bearer_token_provider(foundry_credential, "https://ai.azure.com/.default"),
    )
    try:
        embedding_dimensions, _ = probe_embedding(
            embedding_client,
            settings.embedding_deployment,
            APIStatusError,
            APIConnectionError,
        )
        print(f"  Embedding dimensions: {embedding_dimensions}")
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        embedding_client.close()
        foundry_credential.close()
        return 1

    credential = AzureKeyCredential(settings.search_api_key)
    try:
        with SearchIndexClient(
            endpoint=settings.search_endpoint,
            credential=credential,
            api_version=settings.search_api_version,
        ) as index_client:
            try:
                index = index_client.get_index(settings.search_index_name)
                statistics = index_client.get_index_statistics(settings.search_index_name)
            except ResourceNotFoundError:
                print(f"ERROR: Search index '{settings.search_index_name}' does not exist", file=sys.stderr)
                return 1
            except HttpResponseError as exc:
                print(f"ERROR: Search inspection failed ({describe_http_error(exc)})", file=sys.stderr)
                return 1

        print("\nStatistics")
        print(f"  document count: {statistics.document_count}")
        print(f"  storage bytes: {statistics.storage_size}")
        print(f"  vector index bytes: {getattr(statistics, 'vector_index_size', 'unavailable')}")
        schema_errors, schema_warnings, semantic_name = inspect_schema(
            index,
            embedding_dimensions,
        )
        errors.extend(schema_errors)
        warnings.extend(schema_warnings)

        if statistics.document_count > 0:
            with SearchClient(
                endpoint=settings.search_endpoint,
                index_name=settings.search_index_name,
                credential=credential,
                api_version=settings.search_api_version,
            ) as search_client:
                errors.extend(
                    run_queries(
                        search_client,
                        VectorizedQuery,
                        embedding_client,
                        settings.embedding_deployment,
                        index,
                        args.query,
                        args.top,
                        semantic_name,
                    )
                )
        else:
            errors.append("the index contains no documents")
    finally:
        embedding_client.close()
        foundry_credential.close()

    if warnings:
        print("\nWarnings")
        for warning in warnings:
            print(f"  - {warning}")
    if errors:
        print("\nFailures", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print("\nLive Search checks passed.")
    return 0


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
