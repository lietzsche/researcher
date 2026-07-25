"""Study-document assembly."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from mcp_server.storage import OutputStorage, utc_now


def assemble_study_document(
    topic: str,
    *,
    output_root: str | Path | None = None,
) -> dict[str, Any]:
    """Assemble TOC-ordered section files into one study document."""
    storage = OutputStorage(
        output_root or os.getenv("RESEARCH_OUTPUT_DIR", "./outputs"), topic
    )
    toc = storage.read_json(storage.toc_json_path)
    if not isinstance(toc, list) or not toc:
        raise ValueError(f"TOC must be a non-empty JSON list: {storage.toc_json_path}")
    manifest = storage.load_manifest()
    manifest_sections = {
        section.get("id"): section for section in manifest.get("sections", [])
    }

    lines = [f"# {topic}", "", "## 목차", ""]
    for section in toc:
        lines.append(
            f"- [{section['id']}. {section['title']}](#section-{section['id']})"
        )
        for subsection in section.get("subsections", []):
            lines.append(f"  - {subsection['id']} {subsection['title']}")

    for section in toc:
        section_id = section["id"]
        lines.extend(
            [
                "",
                "---",
                "",
                f'<a id="section-{section_id}"></a>',
                f"## {section_id}. {section['title']}",
                "",
            ]
        )
        state = manifest_sections.get(section_id)
        if state is None:
            lines.append(
                "> **미완료:** manifest.json에 이 섹션 상태가 없습니다. "
                "research_section으로 생성해야 합니다."
            )
            continue
        if state.get("status") != "done":
            lines.append(
                f"> **미완료 ({state.get('status', 'pending')}):** "
                "이 섹션은 아직 리서치되지 않았습니다."
            )
            lines.extend(["", section.get("description", "")])
            continue

        section_path = storage.section_path(section_id, section["title"])
        try:
            content = section_path.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            lines.append(
                "> **파일 누락:** manifest에는 완료로 표시되지만 섹션 파일이 "
                f"없습니다: `{section_path.name}`"
            )
            continue
        lines.append(content)

    document = "\n".join(lines).rstrip() + "\n"
    storage.write_text(storage.study_document_path, document)
    manifest["updated_at"] = utc_now()
    manifest["study_document"] = {
        "path": "study_document.md",
        "generated_at": utc_now(),
    }
    storage.save_manifest(manifest)
    return {
        "study_document_markdown": document,
        "study_document_path": str(storage.study_document_path),
        "manifest": manifest,
    }
