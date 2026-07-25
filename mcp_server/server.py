"""MCP stdio server entry point."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

# DESIGN.md uses `python /absolute/path/mcp_server/server.py`. Ensure absolute
# package imports also work when the module is started by file path.
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
from mcp.server.fastmcp import Context, FastMCP

from mcp_server.assemble import assemble_study_document
from mcp_server.config import load_settings
from mcp_server.research import quick_search as run_quick_search
from mcp_server.research import research_section as run_research_section
from mcp_server.schemas import (
    BuildStudyDocumentInput,
    BuildStudyDocumentOutput,
    GenerateTocInput,
    GenerateTocOutput,
    QuickSearchInput,
    QuickSearchOutput,
    ResearchSectionInput,
    ResearchSectionOutput,
)
from mcp_server.storage import OutputStorage
from mcp_server.toc import generate_toc as run_generate_toc

load_dotenv(override=False)
mcp = FastMCP(
    os.getenv("MCP_SERVER_NAME", "deep-research"),
    instructions=(
        "Build study documents by generating a TOC, independently researching "
        "each section, and assembling the saved section files."
    ),
)


def _tool_error(tool: str, exc: BaseException) -> RuntimeError:
    if isinstance(exc, (ConnectionError, TimeoutError, ValueError, FileNotFoundError)):
        return RuntimeError(f"{tool} failed: {exc}")
    return RuntimeError(f"{tool} failed ({type(exc).__name__}): {exc}")


@mcp.tool(description="Generate and save a reviewable study table of contents.")
async def generate_toc(
    topic: str,
    depth: str = "standard",
    num_sections: int | None = None,
) -> GenerateTocOutput:
    try:
        request = GenerateTocInput(
            topic=topic, depth=depth, num_sections=num_sections
        )
        result = await run_generate_toc(**request.model_dump())
        return GenerateTocOutput.model_validate(result)
    except BaseException as exc:
        raise _tool_error("generate_toc", exc) from exc


@mcp.tool(description="Deeply research one TOC section and save its Markdown file.")
async def research_section(
    topic: str,
    section_id: str,
    force: bool = False,
) -> ResearchSectionOutput:
    try:
        request = ResearchSectionInput(
            topic=topic, section_id=section_id, force=force
        )
        result = await run_research_section(**request.model_dump())
        return ResearchSectionOutput.model_validate(result)
    except BaseException as exc:
        raise _tool_error("research_section", exc) from exc


async def _ensure_toc(request: BuildStudyDocumentInput) -> OutputStorage:
    settings = load_settings()
    storage = OutputStorage(settings.research_output_dir, request.topic)
    if request.force_regenerate or not storage.toc_json_path.is_file():
        await run_generate_toc(
            request.topic,
            depth=request.depth,
            output_root=settings.research_output_dir,
        )
    return storage


def _selected_sections(
    toc: list[dict[str, Any]],
    manifest: dict[str, Any],
    sections_filter: list[str] | None,
    force: bool,
) -> list[dict[str, Any]]:
    valid_ids = {section["id"] for section in toc}
    if sections_filter:
        unknown = set(sections_filter) - valid_ids
        if unknown:
            raise ValueError(
                "Unknown sections_filter ids: " + ", ".join(sorted(unknown))
            )
        selected_ids = set(sections_filter)
    else:
        selected_ids = valid_ids
    statuses = {
        section.get("id"): section.get("status")
        for section in manifest.get("sections", [])
    }
    return [
        section
        for section in toc
        if section["id"] in selected_ids
        and (force or statuses.get(section["id"]) != "done")
    ]


@mcp.tool(
    description=(
        "Generate a TOC if needed, research selected unfinished sections, and "
        "assemble study_document.md."
    )
)
async def build_study_document(
    topic: str,
    depth: str = "standard",
    force_regenerate: bool = False,
    sections_filter: list[str] | None = None,
    ctx: Context | None = None,
) -> BuildStudyDocumentOutput:
    try:
        request = BuildStudyDocumentInput(
            topic=topic,
            depth=depth,
            force_regenerate=force_regenerate,
            sections_filter=sections_filter,
        )
        storage = await _ensure_toc(request)
        toc = storage.read_json(storage.toc_json_path)
        manifest = storage.load_manifest()
        targets = _selected_sections(
            toc, manifest, request.sections_filter, request.force_regenerate
        )
        total = len(targets)
        for index, section in enumerate(targets, start=1):
            await run_research_section(
                request.topic,
                section["id"],
                force=request.force_regenerate,
                output_root=storage.output_root,
            )
            message = f"{index}/{total} 섹션 완료: {section['title']}"
            if ctx is not None:
                ctx.report_progress(index, total, message)
                await ctx.info(message)
        result = assemble_study_document(
            request.topic, output_root=storage.output_root
        )
        return BuildStudyDocumentOutput.model_validate(result)
    except BaseException as exc:
        raise _tool_error("build_study_document", exc) from exc


@mcp.tool(description="Run a lightweight search against local SearXNG.")
async def quick_search(
    query: str,
    num_results: int = 5,
) -> QuickSearchOutput:
    try:
        request = QuickSearchInput(query=query, num_results=num_results)
        result = await run_quick_search(**request.model_dump())
        return QuickSearchOutput.model_validate(result)
    except BaseException as exc:
        raise _tool_error("quick_search", exc) from exc


def main() -> None:
    """Run the server using local stdio transport."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
