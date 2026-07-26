"""Single-worker background queue for research jobs."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Literal

from app.assemble import assemble_study_document
from app.config import Settings
from app.research import research_section
from app.storage import OutputStorage

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ResearchJob:
    kind: Literal["section", "build"]
    topic: str
    section_ids: tuple[str, ...]
    force: bool = False


class SerialJobQueue:
    """Process every research request through exactly one asyncio worker."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._queue: asyncio.Queue[ResearchJob] = asyncio.Queue()
        self._worker: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._worker is None or self._worker.done():
            self._worker = asyncio.create_task(
                self._run(),
                name="deep-research-serial-worker",
            )

    async def stop(self) -> None:
        if self._worker is None:
            return
        self._worker.cancel()
        try:
            await self._worker
        except asyncio.CancelledError:
            pass
        self._worker = None

    async def enqueue_section(
        self,
        topic: str,
        section_id: str,
        *,
        force: bool = False,
    ) -> None:
        storage = OutputStorage(self.settings.research_output_dir, topic)
        storage.update_section(section_id, status="in_progress")
        await self._queue.put(
            ResearchJob(
                kind="section",
                topic=storage.topic,
                section_ids=(section_id,),
                force=force,
            )
        )

    async def enqueue_build(
        self,
        topic: str,
        *,
        sections_filter: list[str] | None = None,
        force_regenerate: bool = False,
    ) -> None:
        storage = OutputStorage(self.settings.research_output_dir, topic)
        toc = storage.read_json(storage.toc_json_path)
        manifest = storage.load_manifest()
        known_ids = [str(section["id"]) for section in toc]
        selected_ids = set(sections_filter or known_ids)
        statuses = {
            str(section.get("id")): section.get("status")
            for section in manifest.get("sections", [])
        }
        targets = tuple(
            section_id
            for section_id in known_ids
            if section_id in selected_ids
            and (force_regenerate or statuses.get(section_id) != "done")
        )
        for section_id in targets:
            storage.update_section(section_id, status="in_progress")
        await self._queue.put(
            ResearchJob(
                kind="build",
                topic=storage.topic,
                section_ids=targets,
                force=force_regenerate,
            )
        )

    async def join(self) -> None:
        """Wait until all queued jobs finish; primarily useful for tests."""
        await self._queue.join()

    async def _run(self) -> None:
        while True:
            job = await self._queue.get()
            try:
                if job.kind == "section":
                    await self._research_one(job, job.section_ids[0])
                else:
                    await self._run_build(job)
            except asyncio.CancelledError:
                raise
            except BaseException:
                logger.exception(
                    "Background %s job failed for topic %r",
                    job.kind,
                    job.topic,
                )
            finally:
                self._queue.task_done()

    async def _research_one(self, job: ResearchJob, section_id: str) -> None:
        storage = OutputStorage(self.settings.research_output_dir, job.topic)
        try:
            result = await asyncio.wait_for(
                research_section(
                    job.topic,
                    section_id,
                    force=job.force,
                    output_root=self.settings.research_output_dir,
                    settings=self.settings,
                ),
                timeout=self.settings.section_timeout_seconds,
            )
            if len(result.get("sources", [])) == 0:
                logger.warning(
                    "Research completed with source_count == 0 for section %s "
                    "in topic %r; status remains done",
                    section_id,
                    job.topic,
                )
        except BaseException:
            try:
                storage.update_section(section_id, status="error")
            except (FileNotFoundError, ValueError):
                logger.exception(
                    "Could not record failed section %s for topic %r",
                    section_id,
                    job.topic,
                )
            raise

    async def _run_build(self, job: ResearchJob) -> None:
        storage = OutputStorage(self.settings.research_output_dir, job.topic)
        semaphore = asyncio.Semaphore(self.settings.max_concurrent_research)

        async def research_with_limit(section_id: str) -> None:
            async with semaphore:
                await self._research_one(job, section_id)

        results = await asyncio.gather(
            *(research_with_limit(section_id) for section_id in job.section_ids),
            return_exceptions=True,
        )
        for section_id, result in zip(job.section_ids, results, strict=True):
            if isinstance(result, BaseException):
                logger.error(
                    "Research failed for section %s in topic %r: %s",
                    section_id,
                    job.topic,
                    result,
                )

        manifest = storage.load_manifest()
        statuses = {
            str(section.get("id")): section.get("status")
            for section in manifest.get("sections", [])
        }
        failed_ids = [
            section_id
            for section_id in job.section_ids
            if statuses.get(section_id) != "done"
        ]
        if failed_ids:
            logger.error(
                "Skipping document assembly for topic %r; sections not done: %s",
                job.topic,
                ", ".join(failed_ids),
            )
            return

        assemble_study_document(
            job.topic,
            output_root=self.settings.research_output_dir,
        )
