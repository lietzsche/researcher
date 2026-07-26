"""Environment-backed application configuration."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field, HttpUrl, ValidationError, model_validator


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
    searxng_url: HttpUrl = HttpUrl("http://localhost:8080")
    site_password: str | None = None
    research_output_dir: Path = Path("./outputs")
    request_timeout_seconds: float = Field(default=30.0, gt=0, le=300)
    section_timeout_seconds: float = Field(default=900.0, ge=1, le=3600)
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
        "searxng_url": os.getenv("SEARXNG_URL", "http://localhost:8080"),
        "site_password": os.getenv("SITE_PASSWORD") or None,
        "research_output_dir": Path(
            os.getenv("RESEARCH_OUTPUT_DIR", "./outputs")
        ),
        "request_timeout_seconds": os.getenv("REQUEST_TIMEOUT_SECONDS", "30"),
        "section_timeout_seconds": os.getenv("SECTION_TIMEOUT_SECONDS", "900"),
        "max_concurrent_research": os.getenv("MAX_CONCURRENT_RESEARCH", "1"),
        "require_api_key": require_api_key,
    }
    try:
        return Settings.model_validate(values)
    except ValidationError as exc:
        messages = "; ".join(error["msg"] for error in exc.errors())
        raise ValueError(f"Invalid configuration: {messages}") from exc
