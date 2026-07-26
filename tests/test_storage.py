from pathlib import Path

from app.storage import OutputStorage, reconcile_stale_jobs, slugify


def test_slugify_keeps_non_latin_scripts_readable() -> None:
    # Study topics are frequently in Korean; the original implementation
    # ASCII-encoded and dropped anything non-Latin, so every Korean topic
    # fell back to an opaque "topic-<hash>" directory name. Confirm the
    # slug stays human-readable instead.
    assert slugify("베이즈 정리") == "베이즈-정리"
    assert slugify("피보나치 수열") == "피보나치-수열"


def test_slugify_lowercases_and_collapses_latin_punctuation() -> None:
    assert slugify("Quantum Mechanics 101!") == "quantum-mechanics-101"
    assert slugify("  spaces   and---dashes  ") == "spaces-and-dashes"


def test_slugify_falls_back_to_hash_for_punctuation_only_input() -> None:
    slug = slugify("!!!")
    assert slug.startswith("topic-")
    assert slugify("!!!") == slug  # stable across calls


def test_pending_manifest_error_and_created_at_preservation(tmp_path: Path) -> None:
    storage = OutputStorage(tmp_path, "Async TOC")
    pending = storage.initialize_pending_manifest(depth="deep")

    assert pending["toc_status"] == "generating"
    assert pending["sections"] == []
    failed = storage.mark_toc_error("LLM failed")
    assert failed["toc_status"] == "error"
    assert failed["toc_error"] == "LLM failed"

    completed = storage.initialize_manifest(
        depth="deep",
        sections=[{"id": "01", "title": "One"}],
        created_at=pending["created_at"],
    )
    assert completed["toc_status"] == "done"
    assert completed["created_at"] == pending["created_at"]


def test_reconcile_stale_jobs_recovers_only_stale_states(tmp_path: Path) -> None:
    stale_toc = OutputStorage(tmp_path, "Stale TOC")
    stale_toc.initialize_pending_manifest(depth="standard")

    stale_section = OutputStorage(tmp_path, "Stale Section")
    stale_section.initialize_manifest(
        depth="standard",
        sections=[
            {"id": "01", "title": "Running"},
            {"id": "02", "title": "Complete"},
        ],
    )
    stale_section.update_section("01", status="in_progress")
    stale_section.update_section("02", status="done")

    healthy = OutputStorage(tmp_path, "Healthy")
    healthy.initialize_manifest(
        depth="standard",
        sections=[{"id": "01", "title": "Pending"}],
    )
    healthy_before = healthy.manifest_path.read_bytes()
    healthy_mtime = healthy.manifest_path.stat().st_mtime_ns

    broken_dir = tmp_path / "broken"
    broken_dir.mkdir()
    (broken_dir / "manifest.json").write_text("{bad json", encoding="utf-8")

    reconcile_stale_jobs(tmp_path)

    recovered_toc = stale_toc.load_manifest()
    assert recovered_toc["toc_status"] == "error"
    assert recovered_toc["toc_error"] == "서버 재시작으로 목차 생성이 중단됨"
    recovered_sections = stale_section.load_manifest()["sections"]
    assert [section["status"] for section in recovered_sections] == [
        "pending",
        "done",
    ]
    assert healthy.manifest_path.read_bytes() == healthy_before
    assert healthy.manifest_path.stat().st_mtime_ns == healthy_mtime
