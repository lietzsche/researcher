from pathlib import Path

import httpx
import pytest
import respx

from mcp_server.config import Settings, load_settings
from mcp_server.research import quick_search, research_section
from mcp_server.storage import OutputStorage


def test_config_requires_an_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("RETRIEVER", "searxng")
    monkeypatch.setenv("SEARXNG_URL", "http://localhost:8080")

    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY or OPENAI_API_KEY"):
        load_settings()


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
