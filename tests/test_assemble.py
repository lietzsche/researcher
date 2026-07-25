from pathlib import Path

from mcp_server.assemble import assemble_study_document
from mcp_server.storage import OutputStorage


def test_assemble_marks_pending_sections(tmp_path: Path) -> None:
    toc = [
        {
            "id": "01",
            "title": "Complete",
            "description": "Finished scope",
            "subsections": [],
        },
        {
            "id": "02",
            "title": "Pending",
            "description": "Unfinished scope",
            "subsections": [],
        },
    ]
    storage = OutputStorage(tmp_path, "Study Topic")
    storage.write_json(storage.toc_json_path, toc)
    storage.initialize_manifest(depth="standard", sections=toc)
    storage.write_text(storage.section_path("01", "Complete"), "Completed body")
    storage.update_section("01", status="done", source_count=0)

    result = assemble_study_document("Study Topic", output_root=tmp_path)
    document = result["study_document_markdown"]

    assert document.index("## 01. Complete") < document.index("## 02. Pending")
    assert "Completed body" in document
    assert "**미완료 (pending):**" in document
    assert "Unfinished scope" in document
    assert Path(result["study_document_path"]).read_text(encoding="utf-8") == document
