import json
from pathlib import Path

import pytest

from app.schemas import GenerateTocOutput
from app.toc import generate_toc


@pytest.mark.asyncio
async def test_generate_toc_validates_and_persists_schema(tmp_path: Path) -> None:
    raw_toc = {
        "sections": [
            {
                "title": "Foundations",
                "description": "Core concepts",
                "subsections": [
                    {"title": "Vocabulary", "description": "Essential terms"}
                ],
            },
            {
                "title": "Applications",
                "description": "Practical use",
                "subsections": [
                    {"title": "Case study", "description": "A worked example"}
                ],
            },
        ]
    }

    result = await generate_toc(
        "Test Topic",
        num_sections=2,
        output_root=tmp_path,
        llm=lambda _prompt: raw_toc,
    )

    output = GenerateTocOutput(
        toc=result["toc"],
        toc_path=result["toc_path"],
    )
    topic_dir = Path(output.toc_path).parent
    assert [section.id for section in output.toc] == ["01", "02"]
    assert output.toc[0].subsections[0].id == "01.1"
    assert json.loads((topic_dir / "toc.json").read_text(encoding="utf-8")) == result["toc"]
    assert "Foundations" in (topic_dir / "toc.md").read_text(encoding="utf-8")
    manifest = json.loads(
        (topic_dir / "manifest.json").read_text(encoding="utf-8")
    )
    assert [section["status"] for section in manifest["sections"]] == [
        "pending",
        "pending",
    ]


@pytest.mark.asyncio
async def test_generate_toc_rejects_wrong_section_count(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="expected 2"):
        await generate_toc(
            "Test Topic",
            num_sections=2,
            output_root=tmp_path,
            llm=lambda _prompt: {
                "sections": [
                    {
                        "title": "Only one",
                        "description": "Incomplete",
                        "subsections": [],
                    }
                ]
            },
        )
