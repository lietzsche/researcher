"""Section research and lightweight web search."""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import Any, Protocol

import httpx

from app.config import Settings, load_settings
from app.storage import OutputStorage


class Researcher(Protocol):
    async def conduct_research(self) -> Any: ...

    async def write_report(self, **kwargs: Any) -> str: ...

    def get_research_sources(self) -> list[dict[str, Any]]: ...


ResearcherFactory = Callable[..., Researcher]
_SOURCE_LINK = re.compile(r"^- \[(?P<title>.+?)]\((?P<url>https?://[^)]+)\)$", re.MULTILINE)
_SEARX_REQUEST_TIMEOUT_PATCHED = False


class _TimeoutBoundRequests:
    """Proxy that defaults ``get`` to a timeout without touching the shared
    ``requests`` module.

    ``searx.py`` does ``import requests``, which binds the same module object
    used by every other consumer of ``import requests`` in this process
    (litellm, other gpt-researcher retrievers/scrapers, ...). Assigning
    ``searx_module.requests.get = ...`` would mutate that shared object and
    silently change timeout behavior process-wide. Rebinding the ``requests``
    *name* inside ``searx_module`` to this proxy instead keeps the patch
    scoped to `SearxSearch.search()`'s own calls.
    """

    def __init__(self, requests_module: Any, timeout: float) -> None:
        self._requests_module = requests_module
        self.get = partial(requests_module.get, timeout=timeout)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._requests_module, name)


def _configure_gpt_researcher(settings: Settings) -> None:
    """Bridge the public config names to GPT-Researcher's environment contract."""
    global _SEARX_REQUEST_TIMEOUT_PATCHED
    if not _SEARX_REQUEST_TIMEOUT_PATCHED:
        from gpt_researcher.retrievers.searx import searx as searx_module

        # The installed retriever omits a timeout on this requests.get call.
        # Apply a narrow, idempotent boundary patch without replacing its
        # search behavior. This is a confirmed defect; whether it caused the
        # reported production hang remains the leading hypothesis, not proof.
        searx_module.requests = _TimeoutBoundRequests(
            searx_module.requests,
            settings.request_timeout_seconds,
        )
        _SEARX_REQUEST_TIMEOUT_PATCHED = True

    # GPT-Researcher 0.16 calls its SearXNG retriever "searx" and expects
    # SEARX_URL. Keep our DESIGN.md-facing names stable at the boundary.
    os.environ["RETRIEVER"] = "searx"
    os.environ["SEARX_URL"] = str(settings.searxng_url).rstrip("/")
    os.environ["FAST_LLM"] = settings.fast_llm
    os.environ["SMART_LLM"] = settings.smart_llm
    os.environ["STRATEGIC_LLM"] = settings.strategic_llm
    os.environ["EMBEDDING"] = settings.embedding
    if settings.deepseek_api_key:
        # GPT-Researcher 0.16 natively parses `deepseek:<model>` and builds a
        # ChatOpenAI client against https://api.deepseek.com. No compatibility
        # fallback or OPENAI_API_KEY alias is needed for this installed version.
        os.environ["DEEPSEEK_API_KEY"] = settings.deepseek_api_key


def _default_researcher_factory(**kwargs: Any) -> Researcher:
    from gpt_researcher import GPTResearcher

    return GPTResearcher(**kwargs)


def _find_section(
    toc: list[dict[str, Any]], section_id: str
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    for section in toc:
        if section.get("id") == section_id:
            siblings = [candidate for candidate in toc if candidate is not section]
            return section, siblings
    raise ValueError(f"Unknown section_id: {section_id}")


def _research_query(
    topic: str,
    section: dict[str, Any],
    siblings: list[dict[str, Any]],
) -> str:
    subsection_scope = "\n".join(
        f"- {item['title']}: {item['description']}"
        for item in section.get("subsections", [])
    )
    excluded_scope = "\n".join(
        f"- {item['title']}: {item['description']}" for item in siblings
    )
    return f"""
Study topic: {topic}
Research only section {section['id']}: {section['title']}
Section scope: {section['description']}

Required subsection coverage:
{subsection_scope or "- No explicit subsections"}

Sibling sections handled independently; avoid duplicating their scope:
{excluded_scope or "- No sibling sections"}

Produce a rigorous, self-contained learning chapter. Explain concepts, evidence,
examples, limitations, and disagreements. Cite web sources with URLs.
""".strip()


def _normalize_sources(raw_sources: list[dict[str, Any]]) -> list[dict[str, str]]:
    sources: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in raw_sources:
        url = str(raw.get("url") or raw.get("href") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        title = str(raw.get("title") or raw.get("name") or url).strip()
        sources.append({"title": title, "url": url})
    return sources


def _with_sources(content: str, sources: list[dict[str, str]]) -> str:
    body = content.strip()
    if not sources or re.search(r"^##\s+(Sources|References|출처|참고문헌)\s*$", body, re.MULTILINE):
        return body
    lines = [body, "", "## Sources", ""]
    lines.extend(f"- [{source['title']}]({source['url']})" for source in sources)
    return "\n".join(lines)


def _sources_from_markdown(content: str) -> list[dict[str, str]]:
    return [
        {"title": match.group("title"), "url": match.group("url")}
        for match in _SOURCE_LINK.finditer(content)
    ]


async def research_section(
    topic: str,
    section_id: str,
    *,
    force: bool = False,
    output_root: str | Path | None = None,
    settings: Settings | None = None,
    researcher_factory: ResearcherFactory | None = None,
) -> dict[str, Any]:
    """Research one TOC section and persist its Markdown chapter."""
    settings = settings or load_settings()
    storage = OutputStorage(output_root or settings.research_output_dir, topic)
    toc = storage.read_json(storage.toc_json_path)
    if not isinstance(toc, list):
        raise ValueError(f"TOC must be a JSON list: {storage.toc_json_path}")
    section, siblings = _find_section(toc, section_id)
    manifest = storage.load_manifest()
    manifest_section = next(
        (item for item in manifest.get("sections", []) if item.get("id") == section_id),
        None,
    )
    if manifest_section is None:
        raise ValueError(f"section_id {section_id!r} is missing from manifest.json")
    section_path = storage.topic_dir / manifest_section["path"]

    if manifest_section.get("status") == "done" and not force:
        try:
            existing = section_path.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise FileNotFoundError(
                f"Section is marked done but its file is missing: {section_path}"
            ) from exc
        return {
            "content_markdown": existing,
            "sources": _sources_from_markdown(existing),
            "section_path": str(section_path),
            "cached": True,
        }

    storage.update_section(section_id, status="in_progress")
    try:
        _configure_gpt_researcher(settings)
        factory = researcher_factory or _default_researcher_factory
        query = _research_query(topic, section, siblings)
        researcher = factory(
            query=query,
            report_type="research_report",
            report_format="markdown",
            parent_query=topic,
            subtopics=siblings,
            verbose=False,
        )
        await researcher.conduct_research()
        content = await researcher.write_report(
            custom_prompt=(
                "Write only this section's learning chapter. Respect the scope and "
                "do not cover sibling sections except for brief cross-references. "
                f"Write your entire response in {settings.output_language}, "
                "regardless of the language of the source material."
            )
        )
        sources = _normalize_sources(researcher.get_research_sources())
        content = _with_sources(content, sources)
        storage.write_text(section_path, content)
        manifest = storage.update_section(
            section_id, status="done", source_count=len(sources)
        )
    except BaseException:
        storage.update_section(section_id, status="error")
        raise

    return {
        "content_markdown": content,
        "sources": sources,
        "section_path": str(section_path),
        "manifest": manifest,
        "cached": False,
    }


async def quick_search(
    query: str,
    *,
    num_results: int = 5,
    settings: Settings | None = None,
    client: httpx.AsyncClient | None = None,
) -> dict[str, list[dict[str, str]]]:
    """Query the local SearXNG JSON endpoint without GPT-Researcher."""
    query = query.strip()
    if not query:
        raise ValueError("query must not be empty")
    if not 1 <= num_results <= 20:
        raise ValueError("num_results must be between 1 and 20")
    settings = settings or load_settings(require_api_key=False)
    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=settings.request_timeout_seconds)
    try:
        response = await client.get(
            f"{str(settings.searxng_url).rstrip('/')}/search",
            params={"q": query, "format": "json"},
        )
        response.raise_for_status()
        payload = response.json()
    except httpx.ConnectError as exc:
        raise ConnectionError(
            f"Cannot connect to SearXNG at {settings.searxng_url}"
        ) from exc
    except httpx.TimeoutException as exc:
        raise TimeoutError(
            f"SearXNG request timed out after {settings.request_timeout_seconds}s"
        ) from exc
    except (httpx.HTTPStatusError, ValueError) as exc:
        raise RuntimeError(f"SearXNG returned an invalid response: {exc}") from exc
    finally:
        if owns_client:
            await client.aclose()

    results = []
    for item in payload.get("results", [])[:num_results]:
        url = str(item.get("url", "")).strip()
        if not url:
            continue
        results.append(
            {
                "title": str(item.get("title") or url).strip(),
                "url": url,
                "snippet": str(item.get("content") or "").strip(),
            }
        )
    return {"results": results}
