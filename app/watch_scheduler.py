"""Single-process scheduler for persisted watch refreshes."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from app.config import Settings
from app.watchlist import WatchStore, refresh_watch

logger = logging.getLogger(__name__)


class WatchScheduler:
    """Poll persisted schedules and serialize refreshes in one worker task."""

    def __init__(self, settings: Settings, *, poll_seconds: float = 30) -> None:
        self.settings = settings
        self.store = WatchStore(settings.research_output_dir)
        self.poll_seconds = poll_seconds
        self._worker: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()
        self._refresh_tasks: set[asyncio.Task[None]] = set()

    async def start(self) -> None:
        self.store.reconcile_interrupted()
        if self._worker is None or self._worker.done():
            self._worker = asyncio.create_task(self._run(), name="watch-scheduler")

    async def stop(self) -> None:
        if self._worker is None:
            return
        self._worker.cancel()
        try:
            await self._worker
        except asyncio.CancelledError:
            pass
        self._worker = None
        for task in self._refresh_tasks:
            task.cancel()
        if self._refresh_tasks:
            await asyncio.gather(*self._refresh_tasks, return_exceptions=True)
        self._refresh_tasks.clear()

    async def trigger(self, slug: str) -> None:
        watch = self.store.get(slug)
        if watch["status"] in {"pending", "running"}:
            raise RuntimeError("Watch refresh is already in progress")
        watch["status"] = "pending"
        watch["last_error"] = None
        self.store.save(watch)
        task = asyncio.create_task(self._refresh(slug), name=f"watch-refresh-{slug}")
        self._refresh_tasks.add(task)
        task.add_done_callback(self._refresh_tasks.discard)

    async def run_due(self, *, now: datetime | None = None) -> list[str]:
        now = now or datetime.now(UTC)
        due: list[str] = []
        for watch in self.store.list():
            next_run = watch.get("next_run_at")
            if (
                next_run
                and watch["status"] not in {"pending", "running"}
                and datetime.fromisoformat(next_run) <= now
            ):
                due.append(watch["slug"])
        for slug in due:
            watch = self.store.get(slug)
            watch["status"] = "pending"
            self.store.save(watch)
            await self._refresh(slug)
        return due

    async def _refresh(self, slug: str) -> None:
        async with self._lock:
            try:
                await refresh_watch(self.store, slug, self.settings)
            except BaseException:
                logger.exception("Watch refresh failed: %s", slug)

    async def _run(self) -> None:
        while True:
            await self.run_due()
            await asyncio.sleep(self.poll_seconds)
