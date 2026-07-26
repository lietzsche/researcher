"""FastAPI application for the personal deep-research web app."""

from __future__ import annotations

import logging
import secrets
import shutil
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Protocol

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict

from app.config import Settings, load_settings
from app.jobs import SerialJobQueue
from app.schemas import GenerateTocInput
from app.storage import OutputStorage
from app.toc import generate_toc

logger = logging.getLogger(__name__)
security = HTTPBasic(auto_error=False)
STATIC_DIR = Path(__file__).parent / "static"


class JobQueue(Protocol):
    """Queue operations consumed by the HTTP layer."""

    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    async def enqueue_section(
        self,
        topic: str,
        section_id: str,
        *,
        force: bool = False,
    ) -> None: ...

    async def enqueue_build(
        self,
        topic: str,
        *,
        sections_filter: list[str] | None = None,
        force_regenerate: bool = False,
    ) -> None: ...


class BuildRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sections_filter: list[str] | None = None
    force_regenerate: bool = False


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _queue(request: Request) -> JobQueue:
    queue = getattr(request.app.state, "job_queue", None)
    if queue is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Background worker is not available",
        )
    return queue


def _topic_storage(settings: Settings, slug: str) -> OutputStorage:
    if not slug or slug in {".", ".."} or "/" in slug or "\\" in slug:
        raise HTTPException(status_code=404, detail="Topic not found")
    topic_dir = settings.research_output_dir.expanduser().resolve() / slug
    manifest_path = topic_dir / "manifest.json"
    if not topic_dir.is_dir() or not manifest_path.is_file():
        raise HTTPException(status_code=404, detail="Topic not found")
    try:
        manifest = OutputStorage(settings.research_output_dir, slug).read_json(
            manifest_path
        )
        topic = str(manifest["topic"])
    except (KeyError, TypeError, ValueError):
        raise HTTPException(status_code=500, detail="Invalid topic manifest") from None
    storage = OutputStorage(settings.research_output_dir, topic)
    if storage.topic_slug != slug:
        raise HTTPException(status_code=500, detail="Invalid topic manifest")
    return storage


def _topic_detail(storage: OutputStorage) -> dict[str, Any]:
    try:
        toc = storage.read_json(storage.toc_json_path)
        manifest = storage.load_manifest()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Topic not found") from None
    return {"toc": toc, "manifest": manifest}


def _topic_summary(manifest: dict[str, Any], topic_dir: Path) -> dict[str, Any]:
    sections = manifest.get("sections", [])
    completed = sum(section.get("status") == "done" for section in sections)
    return {
        "topic": manifest.get("topic"),
        "slug": manifest.get("topic_slug", topic_dir.name),
        "depth": manifest.get("depth"),
        "created_at": manifest.get("created_at"),
        "updated_at": manifest.get("updated_at"),
        "completed_sections": completed,
        "total_sections": len(sections),
        "has_study_document": (topic_dir / "study_document.md").is_file(),
    }


def create_app(
    *,
    settings: Settings | None = None,
    toc_generator: Callable[..., Any] = generate_toc,
    job_queue: JobQueue | None = None,
) -> FastAPI:
    """Build an application, allowing lightweight dependency injection in tests."""

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        application.state.settings = settings or load_settings()
        application.state.settings.research_output_dir.mkdir(
            parents=True, exist_ok=True
        )
        if application.state.settings.site_password is None:
            logger.warning(
                "SITE_PASSWORD is not set; the web application is running "
                "without authentication"
            )
        queue_instance = job_queue or SerialJobQueue(application.state.settings)
        application.state.job_queue = queue_instance
        await queue_instance.start()
        yield
        await queue_instance.stop()

    application = FastAPI(title="Deep Research", lifespan=lifespan)

    @application.middleware("http")
    async def basic_auth(request: Request, call_next: Callable[..., Any]) -> Response:
        current_settings = getattr(request.app.state, "settings", settings)
        password = current_settings.site_password if current_settings else None
        if password:
            credentials: HTTPBasicCredentials | None = await security(request)
            username_ok = credentials is not None and secrets.compare_digest(
                credentials.username.encode("utf-8"),
                b"researcher",
            )
            password_ok = credentials is not None and secrets.compare_digest(
                credentials.password.encode("utf-8"),
                password.encode("utf-8"),
            )
            if not (username_ok and password_ok):
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={"detail": "Invalid authentication credentials"},
                    headers={"WWW-Authenticate": "Basic"},
                )
        return await call_next(request)

    @application.post("/api/topics", status_code=status.HTTP_201_CREATED)
    async def create_topic(payload: GenerateTocInput, request: Request) -> dict[str, Any]:
        current_settings = _settings(request)
        candidate = OutputStorage(current_settings.research_output_dir, payload.topic)
        if candidate.manifest_path.exists():
            raise HTTPException(status_code=409, detail="Topic already exists")
        try:
            return await toc_generator(
                payload.topic,
                depth=payload.depth,
                num_sections=payload.num_sections,
                output_root=current_settings.research_output_dir,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @application.get("/api/topics")
    async def list_topics(request: Request) -> list[dict[str, Any]]:
        root = _settings(request).research_output_dir.expanduser().resolve()
        summaries: list[dict[str, Any]] = []
        if not root.exists():
            return summaries
        for topic_dir in root.iterdir():
            if not topic_dir.is_dir():
                continue
            manifest_path = topic_dir / "manifest.json"
            if not manifest_path.is_file():
                continue
            try:
                manifest = OutputStorage(root, topic_dir.name).read_json(manifest_path)
                if isinstance(manifest, dict):
                    summaries.append(_topic_summary(manifest, topic_dir))
            except (ValueError, OSError):
                logger.exception("Skipping unreadable manifest: %s", manifest_path)
        return sorted(
            summaries,
            key=lambda item: str(item.get("created_at") or ""),
            reverse=True,
        )

    @application.get("/api/topics/{slug}")
    async def get_topic(slug: str, request: Request) -> dict[str, Any]:
        return _topic_detail(_topic_storage(_settings(request), slug))

    @application.post(
        "/api/topics/{slug}/sections/{section_id}/research",
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def start_section_research(
        slug: str,
        section_id: str,
        request: Request,
        force: bool = False,
    ) -> dict[str, str]:
        storage = _topic_storage(_settings(request), slug)
        manifest = storage.load_manifest()
        section = next(
            (item for item in manifest.get("sections", []) if item.get("id") == section_id),
            None,
        )
        if section is None:
            raise HTTPException(status_code=404, detail="Section not found")
        if section.get("status") == "in_progress":
            raise HTTPException(status_code=409, detail="Section is already in progress")
        if section.get("status") == "done" and not force:
            raise HTTPException(
                status_code=409,
                detail="Section is already researched; pass force=true to re-run",
            )
        await _queue(request).enqueue_section(storage.topic, section_id, force=force)
        return {"status": "queued"}

    @application.post(
        "/api/topics/{slug}/build",
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def start_build(
        slug: str,
        payload: BuildRequest,
        request: Request,
    ) -> dict[str, str]:
        storage = _topic_storage(_settings(request), slug)
        manifest = storage.load_manifest()
        if any(
            section.get("status") == "in_progress"
            for section in manifest.get("sections", [])
        ):
            raise HTTPException(status_code=409, detail="Research is already in progress")
        known_ids = {
            str(section.get("id")) for section in manifest.get("sections", [])
        }
        if payload.sections_filter and not set(payload.sections_filter) <= known_ids:
            raise HTTPException(status_code=404, detail="Section not found")
        await _queue(request).enqueue_build(
            storage.topic,
            sections_filter=payload.sections_filter,
            force_regenerate=payload.force_regenerate,
        )
        return {"status": "queued"}

    @application.get("/api/topics/{slug}/document")
    async def get_document(slug: str, request: Request) -> PlainTextResponse:
        storage = _topic_storage(_settings(request), slug)
        if not storage.study_document_path.is_file():
            raise HTTPException(status_code=404, detail="Study document not found")
        return PlainTextResponse(
            storage.study_document_path.read_text(encoding="utf-8"),
            media_type="text/markdown; charset=utf-8",
        )

    @application.get("/api/topics/{slug}/sections/{section_id}")
    async def get_section_document(
        slug: str,
        section_id: str,
        request: Request,
    ) -> PlainTextResponse:
        storage = _topic_storage(_settings(request), slug)
        manifest = storage.load_manifest()
        section = next(
            (
                item
                for item in manifest.get("sections", [])
                if item.get("id") == section_id
            ),
            None,
        )
        if section is None or section.get("status") != "done":
            raise HTTPException(status_code=404, detail="Section document not found")
        section_path = storage.topic_dir / str(section.get("path", ""))
        if not section_path.is_file():
            raise HTTPException(status_code=404, detail="Section document not found")
        return PlainTextResponse(
            section_path.read_text(encoding="utf-8"),
            media_type="text/markdown; charset=utf-8",
        )

    @application.get("/api/topics/{slug}/download")
    async def download_document(slug: str, request: Request) -> FileResponse:
        storage = _topic_storage(_settings(request), slug)
        if not storage.study_document_path.is_file():
            raise HTTPException(status_code=404, detail="Study document not found")
        return FileResponse(
            storage.study_document_path,
            media_type="text/markdown; charset=utf-8",
            filename=f"{slug}.md",
        )

    @application.delete("/api/topics/{slug}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_topic(slug: str, request: Request) -> Response:
        storage = _topic_storage(_settings(request), slug)
        manifest = storage.load_manifest()
        if any(
            section.get("status") == "in_progress"
            for section in manifest.get("sections", [])
        ):
            raise HTTPException(status_code=409, detail="Research is in progress")
        shutil.rmtree(storage.topic_dir)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    application.mount(
        "/",
        StaticFiles(directory=STATIC_DIR, html=True, check_dir=False),
        name="static",
    )
    return application


app = create_app()
