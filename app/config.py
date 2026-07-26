"""Environment-backed application configuration."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field, HttpUrl, ValidationError, model_validator


FALLBACK_RETRIEVER_API_KEY_ENV: dict[str, str] = {
    "tavily": "TAVILY_API_KEY",
    "serper": "SERPER_API_KEY",
    "serpapi": "SERPAPI_API_KEY",
    "searchapi": "SEARCHAPI_API_KEY",
    "exa": "EXA_API_KEY",
}
# Bing is deliberately excluded: Microsoft fully decommissioned the Bing
# Search APIs (including existing instances, not just new signups) on
# 2025-08-11 in favor of the incompatible "Grounding with Bing Search" Azure
# AI product. Verified directly against Microsoft's own lifecycle page.


class Settings(BaseModel):
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    deepseek_api_key: str | None = None
    fast_llm: str = "deepseek:deepseek-v4-flash"
    smart_llm: str = "deepseek:deepseek-v4-flash"
    strategic_llm: str = "deepseek:deepseek-v4-pro"
    # GPT-Researcher's Memory always instantiates an embedding client, and its
    # own default ("openai:...") requires OPENAI_API_KEY even when every LLM
    # call is routed elsewhere. Default to a local, keyless provider so a
    # DeepSeek-only (or Anthropic-only) setup doesn't hard-fail on embeddings.
    embedding: str = "huggingface:sentence-transformers/all-MiniLM-L6-v2"
    output_language: str = "Korean"
    retriever: str = "searxng"
    fallback_retriever: str | None = None
    fallback_retriever_api_key: str | None = None
    searxng_url: HttpUrl = HttpUrl("http://localhost:8080")
    site_password: str | None = None
    research_output_dir: Path = Path("./outputs")
    request_timeout_seconds: float = Field(default=30.0, gt=0, le=300)
    section_timeout_seconds: float = Field(default=900.0, ge=1, le=3600)
    toc_timeout_seconds: float = Field(default=180.0, ge=1, le=1200)
    max_concurrent_research: int = Field(default=1, ge=1, le=5)
    require_api_key: bool = True

    @model_validator(mode="after")
    def validate_provider_and_retriever(self) -> "Settings":
        if self.require_api_key and not (
            self.anthropic_api_key
            or self.openai_api_key
            or self.deepseek_api_key
        ):
            raise ValueError(
                "Missing LLM API key: configure DEEPSEEK_API_KEY, "
                "ANTHROPIC_API_KEY, or OPENAI_API_KEY"
            )
        if self.retriever.lower() != "searxng":
            raise ValueError("RETRIEVER must be 'searxng' for local research")
        if (
            self.fallback_retriever
            and self.fallback_retriever not in FALLBACK_RETRIEVER_API_KEY_ENV
        ):
            allowed = ", ".join(FALLBACK_RETRIEVER_API_KEY_ENV)
            raise ValueError(
                f"FALLBACK_RETRIEVER must be one of: {allowed}"
            )
        if self.fallback_retriever and not self.fallback_retriever_api_key:
            raise ValueError(
                "FALLBACK_RETRIEVER를 설정하려면 "
                "FALLBACK_RETRIEVER_API_KEY도 필요합니다"
            )
        return self


def load_settings(
    *,
    require_api_key: bool = True,
    env_file: str | Path | None = None,
) -> Settings:
    """Load `.env` and validate application settings."""
    load_dotenv(dotenv_path=env_file, override=False)
    values = {
        "anthropic_api_key": os.getenv("ANTHROPIC_API_KEY") or None,
        "openai_api_key": os.getenv("OPENAI_API_KEY") or None,
        "deepseek_api_key": os.getenv("DEEPSEEK_API_KEY") or None,
        "fast_llm": os.getenv("FAST_LLM", Settings.model_fields["fast_llm"].default),
        "smart_llm": os.getenv(
            "SMART_LLM", Settings.model_fields["smart_llm"].default
        ),
        "strategic_llm": os.getenv(
            "STRATEGIC_LLM", Settings.model_fields["strategic_llm"].default
        ),
        "embedding": os.getenv(
            "EMBEDDING", Settings.model_fields["embedding"].default
        ),
        "output_language": os.getenv(
            "OUTPUT_LANGUAGE",
            Settings.model_fields["output_language"].default,
        ),
        # Fixed, not read from os.environ["RETRIEVER"]: _configure_gpt_researcher
        # overwrites that same env var with GPT-Researcher's internal retriever
        # name ("searx") as a side effect, which would make every load_settings()
        # call after the first one in a long-lived process see "searx" and fail
        # this field's "must be searxng" validation. This field only exists to
        # assert the local-only design invariant, so it is never meant to be
        # user-configurable via the environment.
        "retriever": "searxng",
        "fallback_retriever": os.getenv("FALLBACK_RETRIEVER") or None,
        "fallback_retriever_api_key": (
            os.getenv("FALLBACK_RETRIEVER_API_KEY") or None
        ),
        "searxng_url": os.getenv("SEARXNG_URL", "http://localhost:8080"),
        "site_password": os.getenv("SITE_PASSWORD") or None,
        "research_output_dir": Path(
            os.getenv("RESEARCH_OUTPUT_DIR", "./outputs")
        ),
        "request_timeout_seconds": os.getenv("REQUEST_TIMEOUT_SECONDS", "30"),
        "section_timeout_seconds": os.getenv("SECTION_TIMEOUT_SECONDS", "900"),
        "toc_timeout_seconds": os.getenv("TOC_TIMEOUT_SECONDS", "180"),
        "max_concurrent_research": os.getenv("MAX_CONCURRENT_RESEARCH", "1"),
        "require_api_key": require_api_key,
    }
    try:
        return Settings.model_validate(values)
    except ValidationError as exc:
        messages = "; ".join(error["msg"] for error in exc.errors())
        raise ValueError(f"Invalid configuration: {messages}") from exc
