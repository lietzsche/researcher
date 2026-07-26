import os
from functools import partial
from pathlib import Path

import httpx
import pytest
import respx

import app.research as research_module
from app.config import Settings, load_settings
from app.research import (
    _configure_gpt_researcher,
    quick_search,
    research_section,
)
from app.storage import OutputStorage


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


def test_config_defaults_output_language_to_korean(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("OUTPUT_LANGUAGE", raising=False)

    settings = load_settings(
        require_api_key=False,
        env_file=tmp_path / "missing.env",
    )

    assert settings.output_language == "Korean"


def test_config_loads_output_language_from_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("OUTPUT_LANGUAGE", "Japanese")

    settings = load_settings(
        require_api_key=False,
        env_file=tmp_path / "missing.env",
    )

    assert settings.output_language == "Japanese"


def test_config_loads_section_timeout(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("SECTION_TIMEOUT_SECONDS", "120")

    settings = load_settings(
        require_api_key=False,
        env_file=tmp_path / "missing.env",
    )

    assert settings.section_timeout_seconds == 120


def test_config_defaults_and_loads_toc_timeout(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("TOC_TIMEOUT_SECONDS", raising=False)
    assert load_settings(
        require_api_key=False,
        env_file=tmp_path / "missing.env",
    ).toc_timeout_seconds == 180

    monkeypatch.setenv("TOC_TIMEOUT_SECONDS", "75")
    assert load_settings(
        require_api_key=False,
        env_file=tmp_path / "missing.env",
    ).toc_timeout_seconds == 75


@pytest.mark.parametrize("value", [0, 1201])
def test_config_rejects_out_of_range_toc_timeout(value: int) -> None:
    with pytest.raises(ValueError):
        Settings(require_api_key=False, toc_timeout_seconds=value)


def test_config_loads_max_concurrent_research(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("MAX_CONCURRENT_RESEARCH", "4")

    settings = load_settings(
        require_api_key=False,
        env_file=tmp_path / "missing.env",
    )

    assert settings.max_concurrent_research == 4


def test_config_defaults_max_concurrent_research_to_one(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("MAX_CONCURRENT_RESEARCH", raising=False)

    settings = load_settings(
        require_api_key=False,
        env_file=tmp_path / "missing.env",
    )

    assert settings.max_concurrent_research == 1


@pytest.mark.parametrize("value", [0, 6])
def test_config_rejects_out_of_range_research_concurrency(value: int) -> None:
    with pytest.raises(ValueError):
        Settings(require_api_key=False, max_concurrent_research=value)


def test_configure_gpt_researcher_patches_searx_timeout_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from gpt_researcher.retrievers.searx import searx as searx_module

    calls: list[dict[str, object]] = []

    def fake_get(*_args: object, **kwargs: object) -> object:
        calls.append(kwargs)
        return object()

    monkeypatch.setattr(research_module, "_SEARX_REQUEST_TIMEOUT_PATCHED", False)
    monkeypatch.setattr(searx_module.requests, "get", fake_get)
    settings = Settings(
        require_api_key=False,
        request_timeout_seconds=17,
    )

    _configure_gpt_researcher(settings)
    patched_get = searx_module.requests.get
    _configure_gpt_researcher(settings)

    assert isinstance(patched_get, partial)
    assert searx_module.requests.get is patched_get
    patched_get("http://searx.test/search")
    assert calls == [{"timeout": 17}]


def test_configure_gpt_researcher_does_not_patch_shared_requests_module(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The timeout patch must stay scoped to the SearX retriever.

    ``searx.py`` does ``import requests``, which is the *same* module object
    every other importer of ``requests`` in this process sees. Mutating
    ``requests.get`` in place (instead of rebinding the ``requests`` name
    inside the retriever's own module) would silently add a timeout to any
    other unrelated ``requests.get`` call in the process.
    """
    import requests as real_requests
    from gpt_researcher.retrievers.searx import searx as searx_module

    original_get = real_requests.get
    original_searx_requests = searx_module.requests
    monkeypatch.setattr(research_module, "_SEARX_REQUEST_TIMEOUT_PATCHED", False)
    try:
        _configure_gpt_researcher(
            Settings(require_api_key=False, request_timeout_seconds=17)
        )
        assert real_requests.get is original_get
        assert not isinstance(real_requests.get, partial)
    finally:
        searx_module.requests = original_searx_requests


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


def test_config_loads_optional_site_password(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("SITE_PASSWORD", "test-site-password")

    settings = load_settings(
        require_api_key=False,
        env_file=tmp_path / "missing.env",
    )

    assert settings.site_password == "test-site-password"


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


@pytest.mark.asyncio
async def test_research_section_marks_error_when_no_sources_are_found(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A zero-source completion (LLM refusal or ungrounded hallucination when
    GPT-Researcher's own search/scrape step found nothing) must not be
    recorded as "done" -- see DESIGN.md §22. It should stay retry-eligible
    (status="error") instead of silently corrupting the assembled document.
    """

    class RefusingResearcher:
        async def conduct_research(self) -> None:
            return None

        async def write_report(self, **_kwargs: object) -> str:
            return "죄송합니다만, 제공된 문맥(Context)이 비어 있습니다. Context: []"

        def get_research_sources(self) -> list[dict[str, str]]:
            return []

    toc = [
        {
            "id": "01",
            "title": "Target",
            "description": "Target scope",
            "subsections": [],
        }
    ]
    storage = OutputStorage(tmp_path, "Empty Context Topic")
    storage.write_json(storage.toc_json_path, toc)
    storage.initialize_manifest(depth="standard", sections=toc)
    settings = Settings(require_api_key=False)

    result = await research_section(
        "Empty Context Topic",
        "01",
        output_root=tmp_path,
        settings=settings,
        researcher_factory=lambda **_kwargs: RefusingResearcher(),
    )

    section = storage.load_manifest()["sections"][0]
    assert result["sources"] == []
    assert section["status"] == "error"
    assert section["source_count"] == 0
    assert "no sources" in caplog.text
    assert "section 01" in caplog.text
    assert "Empty Context Topic" in caplog.text

    # A subsequent attempt must not hit the done-section cache shortcut --
    # it should call the researcher again for a real retry.
    retried: list[str] = []

    class RetryResearcher:
        async def conduct_research(self) -> None:
            return None

        async def write_report(self, **_kwargs: object) -> str:
            retried.append("called")
            return "Real content this time."

        def get_research_sources(self) -> list[dict[str, str]]:
            return [{"title": "Source", "url": "https://example.com/source"}]

    retry_result = await research_section(
        "Empty Context Topic",
        "01",
        output_root=tmp_path,
        settings=settings,
        researcher_factory=lambda **_kwargs: RetryResearcher(),
    )

    assert retried == ["called"]
    assert retry_result["cached"] is False
    assert storage.load_manifest()["sections"][0]["status"] == "done"


@pytest.mark.asyncio
async def test_research_section_cache_uses_manifest_path_after_title_drift(
    tmp_path: Path,
) -> None:
    original_toc = [
        {
            "id": "01",
            "title": "Original File Title",
            "description": "Original scope",
            "subsections": [],
        }
    ]
    storage = OutputStorage(tmp_path, "Path Cache Topic")
    storage.write_json(storage.toc_json_path, original_toc)
    manifest = storage.initialize_manifest(depth="standard", sections=original_toc)
    actual_path = storage.topic_dir / manifest["sections"][0]["path"]
    storage.write_text(actual_path, "# Cached body from the original path")

    drifted_toc = [
        {
            **original_toc[0],
            "title": "Renamed Metadata Title",
        }
    ]
    storage.write_json(storage.toc_json_path, drifted_toc)
    manifest["sections"][0]["title"] = "Renamed Metadata Title"
    manifest["sections"][0]["status"] = "done"
    storage.save_manifest(manifest)

    result = await research_section(
        "Path Cache Topic",
        "01",
        output_root=tmp_path,
        settings=Settings(require_api_key=False),
        researcher_factory=lambda **_kwargs: pytest.fail("cache was not used"),
    )

    assert result["cached"] is True
    assert result["content_markdown"] == "# Cached body from the original path\n"
    assert Path(result["section_path"]) == actual_path


@pytest.mark.asyncio
async def test_research_section_includes_output_language_in_custom_prompt(
    tmp_path: Path,
) -> None:
    captured: dict[str, str] = {}

    class FakeResearcher:
        async def conduct_research(self) -> None:
            return None

        async def write_report(self, **kwargs: object) -> str:
            captured["custom_prompt"] = str(kwargs["custom_prompt"])
            return "지정된 언어로 작성된 섹션 본문"

        def get_research_sources(self) -> list[dict[str, str]]:
            return []

    toc = [
        {
            "id": "01",
            "title": "언어 지시 검증",
            "description": "최종 결과물의 언어를 검증합니다.",
            "subsections": [],
        }
    ]
    storage = OutputStorage(tmp_path, "언어 설정 테스트")
    storage.write_json(storage.toc_json_path, toc)
    storage.initialize_manifest(depth="standard", sections=toc)
    settings = Settings(
        anthropic_api_key="test-key",
        output_language="Japanese",
    )

    await research_section(
        "언어 설정 테스트",
        "01",
        output_root=tmp_path,
        settings=settings,
        researcher_factory=lambda **_kwargs: FakeResearcher(),
    )

    assert (
        "Write your entire response in Japanese, regardless of the language "
        "of the source material."
        in captured["custom_prompt"]
    )
