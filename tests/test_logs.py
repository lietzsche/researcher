import logging
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.logs import InMemoryLogHandler
from app.main import create_app


class FakeQueue:
    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass


def test_in_memory_handler_assigns_ids_and_discards_oldest_records() -> None:
    handler = InMemoryLogHandler(capacity=2)
    logger = logging.getLogger("tests.bounded-logs")
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    logger.propagate = False
    try:
        logger.info("first")
        logger.warning("second")
        logger.error("third")
    finally:
        logger.removeHandler(handler)

    records = handler.get_records(limit=10)
    assert [record["id"] for record in records] == [2, 3]
    assert [record["message"] for record in records] == ["second", "third"]
    assert records[0]["level"] == "WARNING"
    assert records[0]["logger"] == "tests.bounded-logs"


def test_log_api_returns_only_records_after_cursor(tmp_path: Path) -> None:
    settings = Settings(require_api_key=False, research_output_dir=tmp_path)
    application = create_app(settings=settings, job_queue=FakeQueue())

    with TestClient(application) as client:
        initial = client.get("/api/logs")
        assert initial.status_code == 200
        assert initial.json()
        cursor = initial.json()[-1]["id"]

        logging.getLogger("tests.log-api").warning("cursor regression marker")

        response = client.get(f"/api/logs?after_id={cursor}&limit=10")
        assert response.status_code == 200
        records = response.json()
        assert [record["message"] for record in records] == [
            "cursor regression marker"
        ]
        assert records[0]["id"] > cursor
        assert client.get(f"/api/logs?after_id={records[0]['id']}").json() == []
