"""Persistent watch registration, refresh snapshots, and deterministic diffs."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from app.config import Settings
from app.research import quick_search
from app.storage import OutputStorage, slugify, utc_now

SearchFunction = Callable[..., Awaitable[dict[str, list[dict[str, str]]]]]


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class WatchStore:
    """Persist watches and immutable refresh runs below the output root."""

    def __init__(self, output_root: str | Path) -> None:
        self.root = Path(output_root).expanduser().resolve() / ".watchlist"
        self.watches_dir = self.root / "watches"
        self.runs_dir = self.root / "runs"

    def create(
        self,
        topic: str,
        *,
        interval_minutes: int | None = None,
    ) -> dict[str, Any]:
        topic = topic.strip()
        if not topic:
            raise ValueError("topic must not be empty")
        if interval_minutes is not None and not 5 <= interval_minutes <= 10080:
            raise ValueError("interval_minutes must be between 5 and 10080")
        slug = slugify(topic, fallback_prefix="watch")
        path = self._watch_path(slug)
        if path.exists():
            raise FileExistsError(f"Watch already exists: {slug}")
        now = utc_now()
        watch = {
            "slug": slug,
            "topic": topic,
            "status": "idle",
            "interval_minutes": interval_minutes,
            "next_run_at": self._next_run(now, interval_minutes),
            "created_at": now,
            "updated_at": now,
            "last_error": None,
            "current_run_id": None,
            "previous_run_id": None,
        }
        self.save(watch)
        return watch

    def list(self) -> list[dict[str, Any]]:
        if not self.watches_dir.exists():
            return []
        watches = [self._read(path) for path in self.watches_dir.glob("*.json")]
        return sorted(watches, key=lambda item: item["created_at"], reverse=True)

    def get(self, slug: str) -> dict[str, Any]:
        self._validate_slug(slug)
        return self._read(self._watch_path(slug))

    def save(self, watch: dict[str, Any]) -> None:
        watch["updated_at"] = utc_now()
        payload = json.dumps(watch, ensure_ascii=False, indent=2) + "\n"
        OutputStorage._atomic_write(self._watch_path(str(watch["slug"])), payload)

    def delete(self, slug: str) -> None:
        watch = self.get(slug)
        self._watch_path(slug).unlink()
        for run_id in (watch.get("current_run_id"), watch.get("previous_run_id")):
            if run_id:
                self._run_path(slug, str(run_id)).unlink(missing_ok=True)

    def set_interval(self, slug: str, interval_minutes: int | None) -> dict[str, Any]:
        if interval_minutes is not None and not 5 <= interval_minutes <= 10080:
            raise ValueError("interval_minutes must be between 5 and 10080")
        watch = self.get(slug)
        watch["interval_minutes"] = interval_minutes
        watch["next_run_at"] = self._next_run(utc_now(), interval_minutes)
        self.save(watch)
        return watch

    def load_run(self, slug: str, run_id: str | None) -> dict[str, Any] | None:
        if not run_id:
            return None
        return self._read(self._run_path(slug, run_id))

    def save_run(self, slug: str, run: dict[str, Any]) -> None:
        payload = json.dumps(run, ensure_ascii=False, indent=2) + "\n"
        OutputStorage._atomic_write(self._run_path(slug, str(run["id"])), payload)

    def detail(self, slug: str) -> dict[str, Any]:
        watch = self.get(slug)
        return {
            "watch": watch,
            "current_run": self.load_run(slug, watch.get("current_run_id")),
            "previous_run": self.load_run(slug, watch.get("previous_run_id")),
        }

    def reconcile_interrupted(self) -> None:
        for watch in self.list():
            if watch["status"] in {"pending", "running"}:
                watch["status"] = "error"
                watch["last_error"] = "Refresh interrupted by server restart"
                self.save(watch)

    @staticmethod
    def _next_run(now: str, interval_minutes: int | None) -> str | None:
        if interval_minutes is None:
            return None
        return (_parse_time(now) + timedelta(minutes=interval_minutes)).isoformat()

    def _watch_path(self, slug: str) -> Path:
        return self.watches_dir / f"{slug}.json"

    def _run_path(self, slug: str, run_id: str) -> Path:
        return self.runs_dir / slug / f"{run_id}.json"

    @staticmethod
    def _validate_slug(slug: str) -> None:
        if not slug or slug in {".", ".."} or "/" in slug or "\\" in slug:
            raise FileNotFoundError("Watch not found")

    @staticmethod
    def _read(path: Path) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise FileNotFoundError(f"Watch data not found: {path}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"Watch data must be an object: {path}")
        return value


def compare_findings(
    previous: list[dict[str, str]], current: list[dict[str, str]]
) -> dict[str, Any]:
    """Compare normalized findings by URL with stable, deterministic ordering."""
    old = {item["url"]: item for item in previous}
    new = {item["url"]: item for item in current}
    added = [new[url] for url in sorted(new.keys() - old.keys())]
    removed = [old[url] for url in sorted(old.keys() - new.keys())]
    changed = [
        {"before": old[url], "after": new[url]}
        for url in sorted(old.keys() & new.keys())
        if old[url] != new[url]
    ]
    outcome = "no_change" if not (added or removed or changed) else "changed"
    return {"outcome": outcome, "added": added, "changed": changed, "removed": removed}


async def refresh_watch(
    store: WatchStore,
    slug: str,
    settings: Settings,
    *,
    search: SearchFunction = quick_search,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> dict[str, Any]:
    """Run one watch refresh, persist its snapshot, and retain retry state."""
    watch = store.get(slug)
    if watch["status"] == "running":
        raise RuntimeError("Watch refresh is already running")
    run_id = now().strftime("%Y%m%dT%H%M%S%fZ")
    watch["status"] = "running"
    watch["last_error"] = None
    store.save(watch)
    try:
        payload = await search(watch["topic"], num_results=10, settings=settings)
        findings = payload["results"]
        if not findings:
            raise RuntimeError("Search returned no usable results")
        previous = store.load_run(slug, watch.get("current_run_id"))
        changes = compare_findings(
            previous.get("findings", []) if previous else [], findings
        )
        if previous is None:
            changes["outcome"] = "initial"
        run = {
            "id": run_id,
            "created_at": now().isoformat(),
            "findings": findings,
            "changes": changes,
        }
        store.save_run(slug, run)
        watch["previous_run_id"] = watch.get("current_run_id")
        watch["current_run_id"] = run_id
        watch["status"] = "done"
        watch["next_run_at"] = store._next_run(
            now().isoformat(), watch.get("interval_minutes")
        )
        store.save(watch)
        return run
    except BaseException as exc:
        watch["status"] = "error"
        watch["last_error"] = str(exc)
        store.save(watch)
        raise
