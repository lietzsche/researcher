from pathlib import Path

from app.assemble import assemble_study_document
from app.storage import OutputStorage


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


def test_assemble_uses_manifest_path_after_title_drift(tmp_path: Path) -> None:
    original_toc = [
        {
            "id": "01",
            "title": "Original File Title",
            "description": "Finished scope",
            "subsections": [],
        }
    ]
    storage = OutputStorage(tmp_path, "Drifted Assembly Topic")
    storage.write_json(storage.toc_json_path, original_toc)
    manifest = storage.initialize_manifest(depth="standard", sections=original_toc)
    actual_path = storage.topic_dir / manifest["sections"][0]["path"]
    storage.write_text(actual_path, "Body stored under the original filename")

    storage.write_json(
        storage.toc_json_path,
        [{**original_toc[0], "title": "Renamed Metadata Title"}],
    )
    manifest["sections"][0]["title"] = "Renamed Metadata Title"
    manifest["sections"][0]["status"] = "done"
    storage.save_manifest(manifest)

    result = assemble_study_document(
        "Drifted Assembly Topic",
        output_root=tmp_path,
    )

    assert "## 01. Renamed Metadata Title" in result["study_document_markdown"]
    assert "Body stored under the original filename" in result[
        "study_document_markdown"
    ]


def test_assemble_marks_done_section_with_missing_manifest_path(
    tmp_path: Path,
) -> None:
    toc = [
        {
            "id": "01",
            "title": "Legacy Section",
            "description": "Legacy scope",
            "subsections": [],
        }
    ]
    storage = OutputStorage(tmp_path, "Legacy Manifest Topic")
    storage.write_json(storage.toc_json_path, toc)
    manifest = storage.initialize_manifest(depth="standard", sections=toc)
    manifest["sections"][0]["status"] = "done"
    del manifest["sections"][0]["path"]
    storage.save_manifest(manifest)

    result = assemble_study_document(
        "Legacy Manifest Topic",
        output_root=tmp_path,
    )

    assert "**파일 누락:**" in result["study_document_markdown"]
    assert "섹션 파일 경로가 없습니다." in result["study_document_markdown"]
