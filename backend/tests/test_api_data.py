import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.cricket.ingestion.cricsheet import ingest_path
from app.database.base import Base
from app.database.session import get_session
from app.main import app


@pytest.fixture
def client(match_dir):
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        ingest_path(s, match_dir)

    def override():
        with Session(engine) as s:
            yield s

    app.dependency_overrides[get_session] = override
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_query_endpoint(client):
    r = client.post("/api/v1/analytics/query", json={
        "dataset": "batting_performances", "metrics": ["runs"], "orderBy": [{"field": "runs"}], "limit": 1})
    assert r.status_code == 200
    body = r.json()
    assert body["rows"][0]["player"] == "P2" and body["provenance"]["source"] == "internal_analytics"


def test_query_endpoint_rejects_invalid_dsl(client):
    r = client.post("/api/v1/analytics/query", json={"dataset": "batting_performances", "metrics": ["bogus"]})
    assert r.status_code == 422


def test_player_endpoints(client):
    assert client.get("/api/v1/players/999").status_code == 404
    p = client.get("/api/v1/players/1")
    assert p.status_code == 200
    stats = client.get("/api/v1/players/1/statistics").json()
    assert "batting" in stats and "bowling" in stats and stats["batting"]["provenance"]["coverage"]["matches"] == 1


def test_profile_widget_and_focus_flow(client):
    from app.ai.orchestrator import focus_widget
    from app.widgets.service import widget_service
    from app.widgets.schemas import WidgetSpec

    r = client.post("/api/v1/players/1/profile-widget")
    assert r.status_code == 201
    profile = r.json()
    assert profile["type"] == "player_profile" and "PLAYER_SELECTED" in profile["interactions"]["subscribesTo"]
    assert profile["data"]["extra"]["stats"]["runs"] is not None
    assert client.post("/api/v1/players/999/profile-widget").status_code == 404

    f = client.post(f"/api/v1/widgets/{profile['id']}/focus", json={"entityType": "PLAYER", "entityId": 2})
    assert f.status_code == 200 and f.json()["id"] == profile["id"] and f.json()["title"] != profile["title"]

    assert client.post(f"/api/v1/widgets/{profile['id']}/refresh").json()["id"] == profile["id"]
    assert client.post(f"/api/v1/widgets/{profile['id']}/focus", json={"entityType": "TEAM", "entityId": 2}).status_code == 422
