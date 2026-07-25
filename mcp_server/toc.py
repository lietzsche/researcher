"""Table-of-contents generation."""

from __future__ import annotations

import inspect
import json
import os
import re
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from mcp_server.storage import OutputStorage

TocLlm = Callable[[str], str | dict[str, Any] | Awaitable[str | dict[str, Any]]]
_JSON_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


async def _default_llm(prompt: str) -> str:
    from litellm import acompletion

    model = os.getenv("STRATEGIC_LLM") or os.getenv("SMART_LLM")
    if not model:
        raise ValueError("STRATEGIC_LLM or SMART_LLM must be configured")
    # Project configuration follows GPT-Researcher's `provider:model` format;
    # LiteLLM's direct API uses `provider/model`.
    litellm_model = model.replace(":", "/", 1) if ":" in model else model
    response = await acompletion(
        model=litellm_model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You design rigorous, non-overlapping study curricula. "
                    "Return only a valid JSON object."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.2,
    )
    content = response.choices[0].message.content
    if not content:
        raise RuntimeError("The LLM returned an empty TOC response")
    return content


def _prompt(topic: str, depth: str, num_sections: int) -> str:
    depth_guidance = (
        "Cover foundations, competing perspectives, applications, and advanced "
        "details with substantial depth."
        if depth == "deep"
        else "Cover the essential foundations, major concepts, and applications."
    )
    return f"""
Create a study-oriented table of contents for: {topic}

Produce exactly {num_sections} top-level sections. {depth_guidance}
Sections must be collectively comprehensive and mutually non-overlapping.
Each section needs 2-5 useful subsections. Write in the language of the topic.

Return this exact JSON shape:
{{
  "sections": [
    {{
      "title": "section title",
      "description": "what this section uniquely covers",
      "subsections": [
        {{"title": "subsection title", "description": "learning scope"}}
      ]
    }}
  ]
}}
""".strip()


def _parse_response(raw: str | dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(raw, str):
        cleaned = _JSON_FENCE.sub("", raw.strip())
        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise ValueError(f"LLM returned invalid TOC JSON: {exc}") from exc
    else:
        payload = raw

    sections = payload.get("sections") if isinstance(payload, dict) else None
    if not isinstance(sections, list) or not sections:
        raise ValueError("LLM response must contain a non-empty 'sections' list")

    normalized: list[dict[str, Any]] = []
    for section_index, section in enumerate(sections, start=1):
        if not isinstance(section, dict):
            raise ValueError(f"TOC section {section_index} must be an object")
        title = str(section.get("title", "")).strip()
        description = str(section.get("description", "")).strip()
        subsections = section.get("subsections", [])
        if not title or not description or not isinstance(subsections, list):
            raise ValueError(
                f"TOC section {section_index} needs title, description, and subsections"
            )
        section_id = f"{section_index:02d}"
        normalized_subsections = []
        for subsection_index, subsection in enumerate(subsections, start=1):
            if not isinstance(subsection, dict):
                raise ValueError(
                    f"Subsection {section_id}.{subsection_index} must be an object"
                )
            subtitle = str(subsection.get("title", "")).strip()
            subdescription = str(subsection.get("description", "")).strip()
            if not subtitle or not subdescription:
                raise ValueError(
                    f"Subsection {section_id}.{subsection_index} needs a title "
                    "and description"
                )
            normalized_subsections.append(
                {
                    "id": f"{section_id}.{subsection_index}",
                    "title": subtitle,
                    "description": subdescription,
                }
            )
        normalized.append(
            {
                "id": section_id,
                "title": title,
                "description": description,
                "subsections": normalized_subsections,
            }
        )
    return normalized


def toc_to_markdown(topic: str, sections: list[dict[str, Any]]) -> str:
    lines = [f"# {topic}", "", "## 목차", ""]
    for section in sections:
        lines.extend(
            [
                f"{section['id']}. [{section['title']}](#"
                f"{section['id']}-{_heading_anchor(section['title'])})",
                f"   - {section['description']}",
            ]
        )
        for subsection in section["subsections"]:
            lines.append(
                f"   - {subsection['id']} {subsection['title']}: "
                f"{subsection['description']}"
            )
    return "\n".join(lines)


def _heading_anchor(title: str) -> str:
    return re.sub(r"[^\w\s-]", "", title.lower()).strip().replace(" ", "-")


async def generate_toc(
    topic: str,
    *,
    depth: str = "standard",
    num_sections: int | None = None,
    output_root: str | Path | None = None,
    llm: TocLlm | None = None,
) -> dict[str, Any]:
    """Generate and persist a structured table of contents."""
    topic = topic.strip()
    if not topic:
        raise ValueError("topic must not be empty")
    if depth not in {"standard", "deep"}:
        raise ValueError("depth must be 'standard' or 'deep'")
    target_count = num_sections if num_sections is not None else (10 if depth == "deep" else 6)
    if not 2 <= target_count <= 20:
        raise ValueError("num_sections must be between 2 and 20")

    llm_callable = llm or _default_llm
    raw = llm_callable(_prompt(topic, depth, target_count))
    if inspect.isawaitable(raw):
        raw = await raw
    sections = _parse_response(raw)
    if len(sections) != target_count:
        raise ValueError(
            f"LLM returned {len(sections)} sections; expected {target_count}"
        )

    root = output_root or os.getenv("RESEARCH_OUTPUT_DIR", "./outputs")
    storage = OutputStorage(root, topic)
    storage.ensure_structure()
    storage.write_json(storage.toc_json_path, sections)
    storage.write_text(storage.toc_markdown_path, toc_to_markdown(topic, sections))
    manifest = storage.initialize_manifest(depth=depth, sections=sections)
    return {
        "toc": sections,
        "toc_path": str(storage.toc_json_path),
        "manifest": manifest,
    }
