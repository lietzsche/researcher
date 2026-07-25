"""Environment-backed application configuration."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field, HttpUrl, ValidationError, model_validator


class Settings(BaseModel):
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    fast_llm: str = "anthropic:claude-haiku-4-5-20251001"
    smart_llm: str = "anthropic:claude-sonnet-5"
    strategic_llm: str = "anthropic:claude-sonnet-5"
    retriever: str = "searxng"
    searxng_url: HttpUrl = HttpUrl("http://localhost:8080")
    mcp_server_name: str = "deep-research"
    research_output_dir: Path = Path("./outputs")
    request_timeout_seconds: float = Field(default=30.0, gt=0, le=300)
    require_api_key: bool = True

    @model_validator(mode="after")
    def validate_provider_and_retriever(self) -> "Settings":
        if self.require_api_key and not (
            self.anthropic_api_key or self.openai_api_key
        ):
            raise ValueError(
                "Missing LLM API key: configure ANTHROPIC_API_KEY or OPENAI_API_KEY"
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
        "fast_llm": os.getenv("FAST_LLM", Settings.model_fields["fast_llm"].default),
        "smart_llm": os.getenv(
            "SMART_LLM", Settings.model_fields["smart_llm"].default
        ),
        "strategic_llm": os.getenv(
            "STRATEGIC_LLM", Settings.model_fields["strategic_llm"].default
        ),
        "retriever": os.getenv("RETRIEVER", "searxng"),
        "searxng_url": os.getenv("SEARXNG_URL", "http://localhost:8080"),
        "mcp_server_name": os.getenv("MCP_SERVER_NAME", "deep-research"),
        "research_output_dir": Path(
            os.getenv("RESEARCH_OUTPUT_DIR", "./outputs")
        ),
        "request_timeout_seconds": os.getenv("REQUEST_TIMEOUT_SECONDS", "30"),
        "require_api_key": require_api_key,
    }
    try:
        return Settings.model_validate(values)
    except ValidationError as exc:
        messages = "; ".join(error["msg"] for error in exc.errors())
        raise ValueError(f"Invalid configuration: {messages}") from exc
