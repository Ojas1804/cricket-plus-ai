from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.analytics.cache import execute_query_cached
from app.analytics.query_dsl import AnalyticsQuery
from app.cricket.ingestion.cricsheet import ingest_path
from app.cricket.models import BattingPerformance, DataIngestionLog
from app.main import app
from app.widgets.service import widget_service
from tests.test_ai_pipeline import FakeProvider  # noqa: F401


def q():
    return AnalyticsQuery(dataset="batting_performances", metrics=["runs"], orderBy=[{"field": "runs"}])


def test_cached_result_is_marked_and_invalidated_by_new_ingestion(session, match_dir):
    ingest_path(session, match_dir)
    first = execute_query_cached(session, q())
    assert first.provenance["cached"] is False
    second = execute_query_cached(session, q())
    assert second.provenance["cached"] is True and second.rows == first.rows
    assert second.provenance["executedAt"] == first.provenance["executedAt"]

    session.add(DataIngestionLog(source="cricsheet", dataset="x", ingested_at=datetime.now(timezone.utc), status="COMPLETED"))
    session.commit()
    assert execute_query_cached(session, q()).provenance["cached"] is False


def test_cache_bypass_sees_changed_data(session, match_dir):
    ingest_path(session, match_dir)
    execute_query_cached(session, q())
    session.query(BattingPerformance).update({"runs": 999})
    session.commit()
    assert execute_query_cached(session, q()).rows[0]["runs"] != 999
    assert execute_query_cached(session, q(), use_cache=False).rows[0]["runs"] == 999


def test_cache_can_be_disabled(session, match_dir, monkeypatch):
    ingest_path(session, match_dir)
    monkeypatch.setenv("ANALYTICS_CACHE_TTL_SECONDS", "0")
    from app.core.config import get_settings

    get_settings.cache_clear()
    try:
        assert "cached" not in execute_query_cached(session, q()).provenance
    finally:
        get_settings.cache_clear()


@pytest.fixture
def client():
    widget_service._widgets.clear()
    widget_service.layouts.clear()
    return TestClient(app)


def _spec(id_):
    return {"schemaVersion": "1.0", "id": id_, "type": "text", "title": id_, "data": {"extra": {"text": "hi"}},
            "metadata": {"source": "mock", "lastUpdated": "2026-11-16T10:00:00Z"}}


def test_dashboard_attach_detach_layout(client):
    assert client.get("/api/v1/dashboard").json() == {"widgets": [], "layout": {}}
    r = client.post("/api/v1/dashboard/widgets", json={"widgets": [_spec("a"), _spec("b")]})
    assert r.status_code == 201 and r.json() == {"attached": 2}
    assert client.get("/api/v1/widgets/a").status_code == 200
    assert client.patch("/api/v1/dashboard/layout", json={"layout": {"a": {"x": 1, "y": 2, "w": 3, "h": 4}, "ghost": {"x": 0, "y": 0, "w": 1, "h": 1}}}).status_code == 200
    d = client.get("/api/v1/dashboard").json()
    assert {w["id"] for w in d["widgets"]} == {"a", "b"} and d["layout"] == {"a": {"x": 1, "y": 2, "w": 3, "h": 4}}
    assert client.delete("/api/v1/dashboard/widgets/a").status_code == 204
    assert client.get("/api/v1/widgets/a").status_code == 404


def test_dashboard_validates_specs_and_layout(client):
    bad = _spec("x")
    bad["type"] = "not-a-type"
    assert client.post("/api/v1/dashboard/widgets", json={"widgets": [bad]}).status_code == 422
    assert client.patch("/api/v1/dashboard/layout", json={"layout": {"a": {"x": -1, "y": 0, "w": 1, "h": 1}}}).status_code == 422
    assert client.post("/api/v1/dashboard/widgets", json={"widgets": [_spec(str(i)) for i in range(101)]}).status_code == 422
