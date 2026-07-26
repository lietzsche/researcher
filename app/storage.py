"""Persistent output and manifest management."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import unicodedata
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_SAFE_SLUG = re.compile(r"[^\w]+", re.UNICODE)
_SAFE_SECTION_ID = re.compile(r"^[A-Za-z0-9_-]+$")


def utc_now() -> str:
    """Return an ISO-8601 UTC timestamp."""
    return datetime.now(UTC).isoformat()


def slugify(value: str, *, fallback_prefix: str = "topic") -> str:
    """Convert arbitrary user text to a filesystem-safe, stable slug.

    Keeps non-Latin scripts (Korean, etc.) readable instead of collapsing to
    an opaque hash: only ASCII round-tripped to nothing under NFKD+encode
    (e.g. punctuation-only input) falls back to the hash below.
    """
    normalized = unicodedata.normalize("NFC", value).lower()
    slug = _SAFE_SLUG.sub("-", normalized).strip("-_")
    if slug:
        return slug[:80].strip("-_")
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
    return f"{fallback_prefix}-{digest}"


def section_filename(section_id: str, title: str) -> str:
    """Map a section identifier and title to ``01-title.md``."""
    if not _SAFE_SECTION_ID.fullmatch(section_id):
        raise ValueError(f"Unsafe section id: {section_id!r}")
    return f"{section_id}-{slugify(title, fallback_prefix='section')}.md"


class OutputStorage:
    """Manage one topic's files below the configured output root."""

    def __init__(self, output_root: str | Path, topic: str) -> None:
        if not topic.strip():
            raise ValueError("topic must not be empty")
        self.output_root = Path(output_root).expanduser().resolve()
        self.topic = topic.strip()
        self.topic_slug = slugify(self.topic)
        self.topic_dir = self.output_root / self.topic_slug
        self.sections_dir = self.topic_dir / "sections"
        self.manifest_path = self.topic_dir / "manifest.json"
        self.toc_json_path = self.topic_dir / "toc.json"
        self.toc_markdown_path = self.topic_dir / "toc.md"
        self.study_document_path = self.topic_dir / "study_document.md"

    def ensure_structure(self) -> Path:
        """Create the topic and section directories."""
        self.sections_dir.mkdir(parents=True, exist_ok=True)
        return self.topic_dir

    def read_json(self, path: Path) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise FileNotFoundError(f"Required file does not exist: {path}") from exc
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in {path}: {exc}") from exc

    def write_json(self, path: Path, data: Any) -> None:
        self.ensure_structure()
        payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
        self._atomic_write(path, payload)

    def write_text(self, path: Path, content: str) -> None:
        self.ensure_structure()
        self._atomic_write(path, content.rstrip() + "\n")

    def load_manifest(self) -> dict[str, Any]:
        data = self.read_json(self.manifest_path)
        if not isinstance(data, dict):
            raise ValueError(f"Manifest must be a JSON object: {self.manifest_path}")
        return data

    def save_manifest(self, manifest: dict[str, Any]) -> None:
        self.write_json(self.manifest_path, manifest)

    def initialize_manifest(
        self,
        *,
        depth: str,
        sections: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Create a fresh manifest with each TOC section pending."""
        created_at = utc_now()
        manifest = {
            "topic": self.topic,
            "topic_slug": self.topic_slug,
            "created_at": created_at,
            "updated_at": created_at,
            "depth": depth,
            "sections": [
                {
                    "id": section["id"],
                    "title": section["title"],
                    "status": "pending",
                    "timestamp": None,
                    "source_count": 0,
                    "path": str(
                        Path("sections")
                        / section_filename(section["id"], section["title"])
                    ),
                }
                for section in sections
            ],
        }
        self.save_manifest(manifest)
        return manifest

    def update_section(
        self,
        section_id: str,
        *,
        status: str,
        source_count: int | None = None,
    ) -> dict[str, Any]:
        """Update a section status and persist the manifest atomically."""
        if status not in {"pending", "in_progress", "done", "error"}:
            raise ValueError(f"Unsupported section status: {status}")
        manifest = self.load_manifest()
        for section in manifest.get("sections", []):
            if section.get("id") == section_id:
                section["status"] = status
                section["timestamp"] = utc_now()
                if source_count is not None:
                    section["source_count"] = source_count
                manifest["updated_at"] = utc_now()
                self.save_manifest(manifest)
                return manifest
        raise ValueError(f"Unknown section_id: {section_id}")

    def section_path(self, section_id: str, title: str) -> Path:
        return self.sections_dir / section_filename(section_id, title)

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary_name = tempfile.mkstemp(
            dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            temporary_path.replace(path)
        except BaseException:
            temporary_path.unlink(missing_ok=True)
            raise
