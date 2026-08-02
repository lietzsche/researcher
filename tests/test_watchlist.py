from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.config import Settings
from app.watchlist import WatchStore, compare_findings, refresh_watch


def finding(url: str, title: str, snippet: str = "") -> dict[str, str]:
    return {"url": url, "title": title, "snippet": snippet}


def test_watch_registration_persists_across_store_instances(tmp_path: Path) -> None:
    created = WatchStore(tmp_path).create("Policy updates", interval_minutes=60)

    restored = WatchStore(tmp_path).get(created["slug"])

    assert restored["topic"] == "Policy updates"
    assert restored["status"] == "idle"
    assert restored["interval_minutes"] == 60
    assert restored["next_run_at"] is not None


def test_delete_removes_all_run_history_without_touching_other_watch(
    tmp_path: Path,
) -> None:
    store = WatchStore(tmp_path)
    target = store.create("Delete all history")
    other = store.create("Keep this history")
    for run_id in ("first", "second", "third"):
        store.save_run(
            target["slug"],
            {"id": run_id, "created_at": run_id, "findings": [], "changes": {}},
        )
    target["previous_run_id"] = "second"
    target["current_run_id"] = "third"
    store.save(target)
    store.save_run(
        other["slug"],
        {"id": "other", "created_at": "other", "findings": [], "changes": {}},
    )

    store.delete(target["slug"])

    assert not store._watch_path(target["slug"]).exists()
    assert not (store.runs_dir / target["slug"]).exists()
    assert store.get(other["slug"])["topic"] == "Keep this history"
    assert store.load_run(other["slug"], "other")["id"] == "other"


def test_compare_findings_classifies_added_changed_removed_and_no_change() -> None:
    old = [finding("https://a", "A"), finding("https://b", "Before")]
    new = [finding("https://b", "After"), finding("https://c", "C")]

    changes = compare_findings(old, new)

    assert changes["outcome"] == "changed"
    assert [item["url"] for item in changes["added"]] == ["https://c"]
    assert [item["url"] for item in changes["removed"]] == ["https://a"]
    assert changes["changed"][0]["before"]["title"] == "Before"
    assert changes["changed"][0]["after"]["title"] == "After"
    assert compare_findings(new, list(new))["outcome"] == "no_change"


@pytest.mark.asyncio
async def test_refresh_persists_initial_changed_and_no_change_runs(tmp_path: Path) -> None:
    store = WatchStore(tmp_path)
    watch = store.create("Tracked topic")
    responses = iter(
        [
            [finding("https://a", "A")],
            [finding("https://a", "A2"), finding("https://b", "B")],
            [finding("https://a", "A2"), finding("https://b", "B")],
        ]
    )

    async def search(*_args, **_kwargs):
        return {"results": next(responses)}

    clock = iter(
        datetime(2026, 8, 2, 1, minute, tzinfo=UTC) for minute in range(12)
    )
    settings = Settings(require_api_key=False, research_output_dir=tmp_path)
    first = await refresh_watch(
        store, watch["slug"], settings, search=search, now=lambda: next(clock)
    )
    second = await refresh_watch(
        store, watch["slug"], settings, search=search, now=lambda: next(clock)
    )
    third = await refresh_watch(
        store, watch["slug"], settings, search=search, now=lambda: next(clock)
    )

    assert first["changes"]["outcome"] == "initial"
    assert second["changes"]["outcome"] == "changed"
    assert [item["url"] for item in second["changes"]["added"]] == ["https://b"]
    assert second["changes"]["changed"][0]["after"]["title"] == "A2"
    assert third["changes"]["outcome"] == "no_change"
    detail = WatchStore(tmp_path).detail(watch["slug"])
    assert detail["current_run"]["id"] == third["id"]
    assert detail["previous_run"]["id"] == second["id"]


@pytest.mark.asyncio
async def test_failed_refresh_keeps_snapshot_and_can_retry(tmp_path: Path) -> None:
    store = WatchStore(tmp_path)
    watch = store.create("Retry topic")
    attempts = 0

    async def search(*_args, **_kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("temporary search failure")
        return {"results": [finding("https://ok", "Recovered")]}

    settings = Settings(require_api_key=False, research_output_dir=tmp_path)
    with pytest.raises(RuntimeError, match="temporary search failure"):
        await refresh_watch(store, watch["slug"], settings, search=search)
    assert store.get(watch["slug"])["status"] == "error"
    assert store.get(watch["slug"])["current_run_id"] is None

    result = await refresh_watch(store, watch["slug"], settings, search=search)

    assert result["findings"][0]["url"] == "https://ok"
    assert store.get(watch["slug"])["status"] == "done"


@pytest.mark.asyncio
async def test_empty_search_is_retryable_failure_not_a_snapshot(tmp_path: Path) -> None:
    store = WatchStore(tmp_path)
    watch = store.create("Empty topic")

    async def empty_search(*_args, **_kwargs):
        return {"results": []}

    with pytest.raises(RuntimeError, match="no usable results"):
        await refresh_watch(
            store,
            watch["slug"],
            Settings(require_api_key=False, research_output_dir=tmp_path),
            search=empty_search,
        )

    restored = store.get(watch["slug"])
    assert restored["status"] == "error"
    assert restored["current_run_id"] is None
