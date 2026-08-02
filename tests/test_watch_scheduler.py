import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import app.watch_scheduler as scheduler_module
from app.config import Settings
from app.watch_scheduler import WatchScheduler
from app.watchlist import WatchStore


@pytest.mark.asyncio
async def test_due_schedule_refreshes_and_persists_next_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = Settings(require_api_key=False, research_output_dir=tmp_path)
    scheduler = WatchScheduler(settings)
    watch = scheduler.store.create("Scheduled topic", interval_minutes=5)
    stored = scheduler.store.get(watch["slug"])
    stored["next_run_at"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    scheduler.store.save(stored)

    async def fake_refresh(store, slug, _settings):
        current = store.get(slug)
        current["status"] = "done"
        current["next_run_at"] = (datetime.now(UTC) + timedelta(minutes=5)).isoformat()
        store.save(current)
        return {}

    monkeypatch.setattr(scheduler_module, "refresh_watch", fake_refresh)
    due = await scheduler.run_due()

    assert due == [watch["slug"]]
    assert scheduler.store.get(watch["slug"])["status"] == "done"


@pytest.mark.asyncio
async def test_start_reconciles_interrupted_refresh_and_stop_cancels_worker(
    tmp_path: Path,
) -> None:
    settings = Settings(require_api_key=False, research_output_dir=tmp_path)
    store = WatchStore(tmp_path)
    watch = store.create("Interrupted topic")
    stored = store.get(watch["slug"])
    stored["status"] = "running"
    stored["current_run_id"] = "unfinished"
    store.save(stored)
    scheduler = WatchScheduler(settings, poll_seconds=3600)

    await scheduler.start()
    await scheduler.stop()

    restored = WatchStore(tmp_path).get(watch["slug"])
    assert restored["status"] == "error"
    assert "server restart" in restored["last_error"]


@pytest.mark.asyncio
async def test_manual_trigger_rejects_duplicate_pending_refresh(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = Settings(require_api_key=False, research_output_dir=tmp_path)
    scheduler = WatchScheduler(settings)
    watch = scheduler.store.create("Manual topic")
    release = asyncio.Event()

    async def slow_refresh(*_args, **_kwargs):
        await release.wait()
        return {}

    monkeypatch.setattr(scheduler_module, "refresh_watch", slow_refresh)
    await scheduler.trigger(watch["slug"])

    with pytest.raises(RuntimeError, match="already in progress"):
        await scheduler.trigger(watch["slug"])

    release.set()
    await asyncio.gather(*scheduler._refresh_tasks)
