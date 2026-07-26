"""Bounded in-memory logging support for the local web application."""

from __future__ import annotations

import logging
from collections import deque
from datetime import UTC, datetime
from typing import Any


class InMemoryLogHandler(logging.Handler):
    """Keep recent formatted log records in insertion order."""

    def __init__(self, capacity: int = 1000) -> None:
        super().__init__()
        self._records: deque[dict[str, Any]] = deque(maxlen=capacity)
        self._next_id = 1

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = self.format(record)
            with self.lock:
                entry = {
                    "id": self._next_id,
                    "timestamp": datetime.fromtimestamp(
                        record.created, UTC
                    ).isoformat(),
                    "level": record.levelname,
                    "logger": record.name,
                    "message": message,
                }
                self._next_id += 1
                self._records.append(entry)
        except Exception:
            self.handleError(record)

    def get_records(self, *, after_id: int = 0, limit: int = 200) -> list[dict[str, Any]]:
        """Return a copy of records newer than ``after_id``."""

        with self.lock:
            records = [
                dict(record)
                for record in self._records
                if int(record["id"]) > after_id
            ]
        return records[:limit]
