import asyncio
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook

import app.jobs as jobs_module
from app.config import Settings
from app.jobs import SerialJobQueue
from app.main import create_app
from app.storage import OutputStorage
from app.toc import toc_to_markdown


class FakeQueue:
    def __init__(self) -> None:
        self.started = False
        self.section_jobs: list[tuple[str, str, bool]] = []
        self.build_jobs: list[tuple[str, list[str] | None, bool]] = []

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.started = False

    async def enqueue_section(
        self,
        topic: str,
        section_id: str,
        *,
        force: bool = False,
    ) -> None:
        self.section_jobs.append((topic, section_id, force))

    async def enqueue_build(
        self,
        topic: str,
        *,
        sections_filter: list[str] | None = None,
        force_regenerate: bool = False,
    ) -> None:
        self.build_jobs.append((topic, sections_filter, force_regenerate))


def fake_toc_generator_factory(output_root: Path):
    async def fake_toc_generator(
        topic: str,
        *,
        depth: str,
        num_sections: int | None,
        output_root: Path,
    ) -> dict[str, Any]:
        count = num_sections or (10 if depth == "deep" else 6)
        sections = [
            {
                "id": f"{index:02d}",
                "title": f"Section {index}",
                "description": f"Scope {index}",
                "subsections": [
                    {
                        "id": f"{index:02d}.1",
                        "title": f"Part {index}",
                        "description": f"Part scope {index}",
                    }
                ],
            }
            for index in range(1, count + 1)
        ]
        storage = OutputStorage(output_root, topic)
        storage.write_json(storage.toc_json_path, sections)
        storage.write_text(
            storage.toc_markdown_path,
            toc_to_markdown(topic, sections),
        )
        manifest = storage.initialize_manifest(depth=depth, sections=sections)
        return {
            "toc": sections,
            "toc_path": str(storage.toc_json_path),
            "manifest": manifest,
        }

    return fake_toc_generator


@pytest.fixture
def api_client(tmp_path: Path) -> tuple[TestClient, FakeQueue, Settings]:
    settings = Settings(require_api_key=False, research_output_dir=tmp_path)
    queue = FakeQueue()
    application = create_app(
        settings=settings,
        toc_generator=fake_toc_generator_factory(tmp_path),
        job_queue=queue,
    )
    with TestClient(application) as client:
        yield client, queue, settings


def test_all_topic_routes(api_client: tuple[TestClient, FakeQueue, Settings]) -> None:
    client, queue, settings = api_client

    created = client.post(
        "/api/topics",
        json={"topic": "API Test Topic", "depth": "standard", "num_sections": 2},
    )
    assert created.status_code == 201
    slug = created.json()["manifest"]["topic_slug"]

    topics = client.get("/api/topics")
    assert topics.status_code == 200
    assert topics.json() == [
        {
            "topic": "API Test Topic",
            "slug": slug,
            "depth": "standard",
            "created_at": created.json()["manifest"]["created_at"],
            "updated_at": created.json()["manifest"]["updated_at"],
            "completed_sections": 0,
            "total_sections": 2,
            "has_study_document": False,
        }
    ]

    detail = client.get(f"/api/topics/{slug}")
    assert detail.status_code == 200
    assert len(detail.json()["toc"]) == 2
    assert detail.json()["manifest"]["sections"][0]["status"] == "pending"

    section = client.post(f"/api/topics/{slug}/sections/01/research")
    assert section.status_code == 202
    assert section.json() == {"status": "queued"}
    assert queue.section_jobs == [("API Test Topic", "01", False)]

    build = client.post(
        f"/api/topics/{slug}/build",
        json={"sections_filter": ["02"], "force_regenerate": True},
    )
    assert build.status_code == 202
    assert build.json() == {"status": "queued"}
    assert queue.build_jobs == [("API Test Topic", ["02"], True)]

    storage = OutputStorage(settings.research_output_dir, "API Test Topic")
    storage.write_text(storage.study_document_path, "# Finished document")
    manifest = storage.load_manifest()
    manifest["study_document"] = {"path": "study_document.md"}
    storage.save_manifest(manifest)
    first_section = manifest["sections"][0]
    storage.write_text(
        storage.topic_dir / first_section["path"],
        "# Section 1\n\nBody text.\n\n## Sources\n\n"
        "- [Example source](https://example.com/source)",
    )
    storage.update_section("01", status="done", source_count=1)

    document = client.get(f"/api/topics/{slug}/document")
    assert document.status_code == 200
    assert document.text == "# Finished document\n"
    assert document.headers["content-type"] == "text/markdown; charset=utf-8"

    download = client.get(f"/api/topics/{slug}/download")
    assert download.status_code == 200
    assert download.content == b"# Finished document\n"
    assert download.headers["content-type"] == "text/markdown; charset=utf-8"
    assert "attachment" in download.headers["content-disposition"]

    markdown_download = client.get(f"/api/topics/{slug}/download?format=markdown")
    assert markdown_download.content == download.content
    assert markdown_download.headers["content-type"] == download.headers["content-type"]

    excel_download = client.get(f"/api/topics/{slug}/download?format=excel")
    assert excel_download.status_code == 200
    assert excel_download.headers["content-type"] == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert f'filename="{slug}.xlsx"' in excel_download.headers["content-disposition"]
    workbook = load_workbook(BytesIO(excel_download.content))
    assert workbook.sheetnames == ["목차", "본문", "출처"]
    assert workbook["목차"]["B2"].value == "Section 1"
    assert "Body text." in workbook["본문"]["C2"].value
    assert workbook["본문"]["C2"].alignment.wrap_text is True
    assert workbook["출처"]["B2"].value == "Example source"
    assert workbook["출처"]["C2"].value == "https://example.com/source"

    assert client.get(f"/api/topics/{slug}/download?format=pdf").status_code == 422

    deleted = client.delete(f"/api/topics/{slug}")
    assert deleted.status_code == 204
    assert not storage.topic_dir.exists()
    assert client.get(f"/api/topics/{slug}").status_code == 404


def test_api_reports_not_found_and_conflict(
    api_client: tuple[TestClient, FakeQueue, Settings],
) -> None:
    client, _, settings = api_client
    assert client.get("/api/topics/missing").status_code == 404

    created = client.post(
        "/api/topics",
        json={"topic": "Conflict Topic", "depth": "standard", "num_sections": 2},
    )
    slug = created.json()["manifest"]["topic_slug"]
    assert client.post(
        "/api/topics",
        json={"topic": "Conflict Topic", "depth": "standard", "num_sections": 2},
    ).status_code == 409

    storage = OutputStorage(settings.research_output_dir, "Conflict Topic")
    storage.update_section("01", status="in_progress")
    duplicate = client.post(f"/api/topics/{slug}/sections/01/research")
    assert duplicate.status_code == 409
    assert client.post(f"/api/topics/{slug}/build", json={}).status_code == 409
    assert client.delete(f"/api/topics/{slug}").status_code == 409
    assert (
        client.post(f"/api/topics/{slug}/sections/99/research").status_code == 404
    )


def test_research_section_rejects_redo_of_done_section_without_force(
    api_client: tuple[TestClient, FakeQueue, Settings],
) -> None:
    client, queue, settings = api_client
    created = client.post(
        "/api/topics",
        json={"topic": "Done Section Topic", "depth": "standard", "num_sections": 2},
    )
    slug = created.json()["manifest"]["topic_slug"]
    storage = OutputStorage(settings.research_output_dir, "Done Section Topic")
    storage.update_section("01", status="done")

    # Without force: rejected, and no job is queued -- clicking an already
    # "done" section must not silently re-spend API budget on a full redo.
    rejected = client.post(f"/api/topics/{slug}/sections/01/research")
    assert rejected.status_code == 409
    assert queue.section_jobs == []

    # With force=true: allowed, and the queue receives the force flag.
    forced = client.post(f"/api/topics/{slug}/sections/01/research?force=true")
    assert forced.status_code == 202
    assert queue.section_jobs == [("Done Section Topic", "01", True)]


def test_get_section_document_only_returns_completed_sections(
    api_client: tuple[TestClient, FakeQueue, Settings],
) -> None:
    client, _, settings = api_client
    created = client.post(
        "/api/topics",
        json={"topic": "Section Document Topic", "depth": "standard", "num_sections": 2},
    )
    slug = created.json()["manifest"]["topic_slug"]
    storage = OutputStorage(settings.research_output_dir, "Section Document Topic")
    manifest = storage.update_section("01", status="done")
    completed_section = manifest["sections"][0]
    storage.write_text(
        storage.section_path("01", completed_section["title"]),
        "# 완료된 섹션\n\n한국어 본문",
    )

    completed = client.get(f"/api/topics/{slug}/sections/01")
    assert completed.status_code == 200
    assert completed.text == "# 완료된 섹션\n\n한국어 본문\n"
    assert completed.headers["content-type"] == "text/markdown; charset=utf-8"

    assert client.get(f"/api/topics/{slug}/sections/02").status_code == 404
    assert client.get(f"/api/topics/{slug}/sections/99").status_code == 404


def test_get_section_document_uses_manifest_path_after_title_drift(
    api_client: tuple[TestClient, FakeQueue, Settings],
) -> None:
    client, _, settings = api_client
    created = client.post(
        "/api/topics",
        json={"topic": "Drifted API Topic", "depth": "standard", "num_sections": 2},
    )
    slug = created.json()["manifest"]["topic_slug"]
    storage = OutputStorage(settings.research_output_dir, "Drifted API Topic")
    manifest = storage.load_manifest()
    section = manifest["sections"][0]
    actual_path = storage.topic_dir / section["path"]
    storage.write_text(actual_path, "# Body under the original filename")
    section["title"] = "Renamed Metadata Title"
    section["status"] = "done"
    storage.save_manifest(manifest)

    response = client.get(f"/api/topics/{slug}/sections/01")

    assert response.status_code == 200
    assert response.text == "# Body under the original filename\n"


def test_basic_auth_protects_api_and_static_frontend(tmp_path: Path) -> None:
    settings = Settings(
        require_api_key=False,
        research_output_dir=tmp_path,
        site_password="correct horse battery staple",
    )
    application = create_app(settings=settings, job_queue=FakeQueue())
    with TestClient(application) as client:
        assert client.get("/").status_code == 401
        assert client.get("/api/topics").status_code == 401
        assert client.get("/api/topics", auth=("researcher", "wrong")).status_code == 401

        authorized = client.get(
            "/api/topics",
            auth=("researcher", "correct horse battery staple"),
        )
        assert authorized.status_code == 200
        assert authorized.json() == []
        assert client.get(
            "/",
            auth=("researcher", "correct horse battery staple"),
        ).status_code == 200


def test_static_frontend_is_served_without_password(
    api_client: tuple[TestClient, FakeQueue, Settings],
) -> None:
    client, _, _ = api_client
    assert client.get("/").status_code == 200
    assert client.get("/app.js").status_code == 200
    assert client.get("/style.css").status_code == 200


@pytest.mark.asyncio
async def test_job_queue_never_runs_research_in_parallel(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = OutputStorage(tmp_path, "Serial Topic")
    sections = [
        {"id": "01", "title": "One"},
        {"id": "02", "title": "Two"},
    ]
    storage.write_json(storage.toc_json_path, sections)
    storage.initialize_manifest(depth="standard", sections=sections)
    active = 0
    maximum_active = 0

    async def fake_research(
        topic: str,
        section_id: str,
        **_kwargs: Any,
    ) -> dict[str, Any]:
        nonlocal active, maximum_active
        active += 1
        maximum_active = max(maximum_active, active)
        await asyncio.sleep(0.01)
        storage.update_section(section_id, status="done")
        active -= 1
        return {}

    monkeypatch.setattr(jobs_module, "research_section", fake_research)
    queue = SerialJobQueue(
        Settings(require_api_key=False, research_output_dir=tmp_path)
    )
    await queue.start()
    try:
        await queue.enqueue_section("Serial Topic", "01")
        await queue.enqueue_section("Serial Topic", "02")
        await queue.join()
    finally:
        await queue.stop()

    assert maximum_active == 1
    assert [
        section["status"] for section in storage.load_manifest()["sections"]
    ] == ["done", "done"]


@pytest.mark.asyncio
async def test_job_queue_timeout_marks_error_and_processes_next_job(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = OutputStorage(tmp_path, "Timeout Topic")
    sections = [
        {"id": "01", "title": "Hangs"},
        {"id": "02", "title": "Continues"},
    ]
    storage.write_json(storage.toc_json_path, sections)
    storage.initialize_manifest(depth="standard", sections=sections)

    async def fake_research(
        topic: str,
        section_id: str,
        **_kwargs: Any,
    ) -> dict[str, Any]:
        if section_id == "01":
            await asyncio.sleep(1)
        storage.update_section(section_id, status="done")
        return {}

    monkeypatch.setattr(jobs_module, "research_section", fake_research)
    settings = Settings(require_api_key=False, research_output_dir=tmp_path)
    settings.section_timeout_seconds = 0.01
    queue = SerialJobQueue(settings)
    await queue.start()
    try:
        await queue.enqueue_section("Timeout Topic", "01")
        await queue.enqueue_section("Timeout Topic", "02")
        await queue.join()
    finally:
        await queue.stop()

    assert [
        section["status"] for section in storage.load_manifest()["sections"]
    ] == ["error", "done"]
