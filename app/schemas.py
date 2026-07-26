"""Pydantic schemas shared by the research services and HTTP API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Depth = Literal["standard", "deep"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TocSubsection(StrictModel):
    id: str
    title: str
    description: str


class TocSection(StrictModel):
    id: str
    title: str
    description: str
    subsections: list[TocSubsection] = Field(default_factory=list)


class Source(StrictModel):
    title: str
    url: str


class SearchResult(Source):
    snippet: str


class GenerateTocInput(StrictModel):
    topic: str = Field(min_length=1)
    depth: Depth = "standard"
    num_sections: int | None = Field(default=None, ge=2, le=20)


class GenerateTocOutput(StrictModel):
    toc: list[TocSection]
    toc_path: str


class ResearchSectionInput(StrictModel):
    topic: str = Field(min_length=1)
    section_id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    force: bool = False


class ResearchSectionOutput(StrictModel):
    content_markdown: str
    sources: list[Source]
    section_path: str
    cached: bool = False


class BuildStudyDocumentInput(StrictModel):
    topic: str = Field(min_length=1)
    depth: Depth = "standard"
    force_regenerate: bool = False
    sections_filter: list[str] | None = None


class BuildStudyDocumentOutput(StrictModel):
    study_document_markdown: str
    study_document_path: str
    manifest: dict[str, Any]


class QuickSearchInput(StrictModel):
    query: str = Field(min_length=1)
    num_results: int = Field(default=5, ge=1, le=20)


class QuickSearchOutput(StrictModel):
    results: list[SearchResult]
