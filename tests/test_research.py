import os
from pathlib import Path

import httpx
import pytest
import respx

from mcp_server.config import Settings, load_settings
from mcp_server.research import (
    _configure_gpt_researcher,
    quick_search,
    research_section,
)
from mcp_server.storage import OutputStorage


def test_config_requires_an_api_key(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("RETRIEVER", "searxng")
    monkeypatch.setenv("SEARXNG_URL", "http://localhost:8080")

    with pytest.raises(ValueError, match="DEEPSEEK_API_KEY"):
        load_settings(env_file=tmp_path / "missing.env")


def test_config_accepts_deepseek_key_only(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-deepseek-key")
    monkeypatch.setenv("RETRIEVER", "searxng")
    monkeypatch.setenv("SEARXNG_URL", "http://localhost:8080")
    monkeypatch.delenv("FAST_LLM", raising=False)
    monkeypatch.delenv("SMART_LLM", raising=False)
    monkeypatch.delenv("STRATEGIC_LLM", raising=False)

    settings = load_settings(env_file=tmp_path / "missing.env")

    assert settings.deepseek_api_key == "test-deepseek-key"
    assert settings.fast_llm == "deepseek:deepseek-v4-flash"
    assert settings.smart_llm == "deepseek:deepseek-v4-flash"
    assert settings.strategic_llm == "deepseek:deepseek-v4-pro"


def test_configure_gpt_researcher_uses_native_deepseek_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    settings = Settings(deepseek_api_key="test-deepseek-key")

    _configure_gpt_researcher(settings)

    assert settings.fast_llm == "deepseek:deepseek-v4-flash"
    assert settings.smart_llm == "deepseek:deepseek-v4-flash"
    assert settings.strategic_llm == "deepseek:deepseek-v4-pro"
    assert os.environ["DEEPSEEK_API_KEY"] == "test-deepseek-key"


def test_configure_gpt_researcher_defaults_to_keyless_local_embedding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # GPT-Researcher's Memory always builds an embedding client, and its own
    # default provider is "openai:...", which raises OpenAIError when only
    # DEEPSEEK_API_KEY/ANTHROPIC_API_KEY is configured. Confirm we override it
    # with a provider that needs no API key.
    monkeypatch.delenv("EMBEDDING", raising=False)
    settings = Settings(deepseek_api_key="test-deepseek-key")

    _configure_gpt_researcher(settings)

    assert os.environ["EMBEDDING"] == "huggingface:sentence-transformers/all-MiniLM-L6-v2"


@respx.mock
@pytest.mark.asyncio
async def test_quick_search_uses_searxng_json_api() -> None:
    route = respx.get("http://searx.test/search").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": "First",
                        "url": "https://example.com/1",
                        "content": "First snippet",
                    },
                    {
                        "title": "Second",
                        "url": "https://example.com/2",
                        "content": "Second snippet",
                    },
                ]
            },
        )
    )
    settings = Settings(
        require_api_key=False,
        searxng_url="http://searx.test",
    )

    result = await quick_search("test query", num_results=1, settings=settings)

    assert route.called
    assert route.calls.last.request.url.params["format"] == "json"
    assert result == {
        "results": [
            {
                "title": "First",
                "url": "https://example.com/1",
                "snippet": "First snippet",
            }
        ]
    }


@pytest.mark.asyncio
async def test_research_section_passes_sibling_scope_and_caches(
    tmp_path: Path,
) -> None:
    captured: dict[str, str] = {}

    class FakeResearcher:
        def __init__(self, **kwargs: object) -> None:
            captured["query"] = str(kwargs["query"])

        async def conduct_research(self) -> None:
            return None

        async def write_report(self, **_kwargs: object) -> str:
            return "Section body"

        def get_research_sources(self) -> list[dict[str, str]]:
            return [{"title": "Source", "url": "https://example.com/source"}]

    toc = [
        {
            "id": "01",
            "title": "Target",
            "description": "Target scope",
            "subsections": [],
        },
        {
            "id": "02",
            "title": "Sibling",
            "description": "Excluded sibling scope",
            "subsections": [],
        },
    ]
    storage = OutputStorage(tmp_path, "Topic")
    storage.write_json(storage.toc_json_path, toc)
    storage.initialize_manifest(depth="standard", sections=toc)
    settings = Settings(
        anthropic_api_key="test-key",
        searxng_url="http://localhost:8080",
    )

    first = await research_section(
        "Topic",
        "01",
        output_root=tmp_path,
        settings=settings,
        researcher_factory=FakeResearcher,
    )
    second = await research_section(
        "Topic",
        "01",
        output_root=tmp_path,
        settings=settings,
        researcher_factory=lambda **_kwargs: pytest.fail("cache was not used"),
    )

    assert "Sibling" in captured["query"]
    assert "Excluded sibling scope" in captured["query"]
    assert first["sources"] == [
        {"title": "Source", "url": "https://example.com/source"}
    ]
    assert second["cached"] is True
    assert storage.load_manifest()["sections"][0]["status"] == "done"
