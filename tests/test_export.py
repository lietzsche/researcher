from pathlib import Path

from openpyxl import load_workbook

from app.export import _EXCEL_CELL_CHAR_LIMIT, build_excel_workbook
from app.storage import OutputStorage


def _make_topic(tmp_path: Path, *, section_body: str) -> OutputStorage:
    storage = OutputStorage(tmp_path, "Excel Limits")
    sections = [{"id": "01", "title": "Section 1", "description": "desc"}]
    storage.write_json(storage.toc_json_path, sections)
    manifest = storage.initialize_manifest(depth="standard", sections=sections)
    section_path = storage.topic_dir / manifest["sections"][0]["path"]
    storage.write_text(section_path, section_body)
    storage.update_section("01", status="done", source_count=1)
    return storage


def test_build_excel_workbook_keeps_short_body_intact(tmp_path: Path) -> None:
    storage = _make_topic(tmp_path, section_body="short body")

    workbook = load_workbook(build_excel_workbook(storage.topic, storage))

    assert workbook["본문"]["C2"].value.strip() == "short body"


def test_build_excel_workbook_truncates_bodies_over_the_cell_limit(
    tmp_path: Path,
) -> None:
    long_body = "x" * (_EXCEL_CELL_CHAR_LIMIT + 5000) + "\n\n## Sources\n\n- [S](https://example.com)"
    storage = _make_topic(tmp_path, section_body=long_body)

    workbook = load_workbook(build_excel_workbook(storage.topic, storage))

    cell_value = workbook["본문"]["C2"].value
    assert len(cell_value) <= _EXCEL_CELL_CHAR_LIMIT
    assert "엑셀 셀 글자 수 제한" in cell_value
    # Sources are extracted from the full, untruncated content.
    assert workbook["출처"]["C2"].value == "https://example.com"
