"""Environment-backed application configuration."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

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
    retriever: str = "searxng"
    searxng_url: HttpUrl = HttpUrl("http://localhost:8080")
    mcp_server_name: str = "deep-research"
    mcp_transport: Literal["stdio", "streamable-http"] = "stdio"
    mcp_host: str = "127.0.0.1"
    mcp_port: int = Field(default=8765, ge=1, le=65535)
    mcp_bearer_token: str | None = None
    research_output_dir: Path = Path("./outputs")
    request_timeout_seconds: float = Field(default=30.0, gt=0, le=300)
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
        if self.mcp_transport != "stdio" and not self.mcp_bearer_token:
            raise ValueError(
                "MCP_BEARER_TOKEN is required when MCP_TRANSPORT is not 'stdio'"
            )
        if self.mcp_host not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError(
                "MCP_HOST must remain loopback-only; use cloudflared for exposure"
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
        # Fixed, not read from os.environ["RETRIEVER"]: _configure_gpt_researcher
        # overwrites that same env var with GPT-Researcher's internal retriever
        # name ("searx") as a side effect, which would make every load_settings()
        # call after the first one in a long-lived process see "searx" and fail
        # this field's "must be searxng" validation. This field only exists to
        # assert the local-only design invariant, so it is never meant to be
        # user-configurable via the environment.
        "retriever": "searxng",
        "searxng_url": os.getenv("SEARXNG_URL", "http://localhost:8080"),
        "mcp_server_name": os.getenv("MCP_SERVER_NAME", "deep-research"),
        "mcp_transport": os.getenv("MCP_TRANSPORT", "stdio"),
        "mcp_host": os.getenv("MCP_HOST", "127.0.0.1"),
        "mcp_port": os.getenv("MCP_PORT", "8765"),
        "mcp_bearer_token": os.getenv("MCP_BEARER_TOKEN") or None,
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
