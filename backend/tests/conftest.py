import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.cricket.models  # noqa: F401
from app.database.base import Base


def _d(batter, bowler, bat_runs, extras=None, wickets=None):
    extra_total = sum(extras.values()) if extras else 0
    d = {"batter": batter, "bowler": bowler, "non_striker": "P3",
         "runs": {"batter": bat_runs, "extras": extra_total, "total": bat_runs + extra_total}}
    if extras:
        d["extras"] = extras
    if wickets:
        d["wickets"] = wickets
    return d


MATCH = {
    "info": {
        "dates": ["2024-03-01"], "match_type": "T20", "season": "2024", "team_type": "club",
        "event": {"name": "Test League"}, "teams": ["Alpha", "Beta"], "venue": "Ground 1", "city": "Town",
        "outcome": {"winner": "Alpha"},
        "registry": {"people": {"P1": "id-p1", "P2": "id-p2", "P3": "id-p3", "Z": "id-z", "Y": "id-y"}},
    },
    "innings": [
        {"team": "Alpha", "overs": [
            {"over": 0, "deliveries": [
                _d("P1", "Z", 4),
                _d("P1", "Z", 0, {"wides": 1}),
                _d("P1", "Z", 1, {"noballs": 1}),
                _d("P1", "Z", 0, {"legbyes": 1}),
                _d("P1", "Z", 0, wickets=[{"player_out": "P1", "kind": "bowled"}]),
                _d("P2", "Z", 6),
                _d("P2", "Z", 2),
            ]},
            {"over": 1, "deliveries": [_d("P2", "Y", 0) for _ in range(5)] + [
                _d("P2", "Y", 0, wickets=[{"player_out": "P2", "kind": "run out"}])]},
        ]},
        {"team": "Beta", "super_over": True, "overs": [{"over": 0, "deliveries": [_d("P3", "Z", 1)]}]},
    ],
}


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


@pytest.fixture
def match_dir(tmp_path):
    (tmp_path / "1001.json").write_text(json.dumps(MATCH))
    (tmp_path / "bad.json").write_text(json.dumps({"info": {"teams": ["A", "B"]}, "innings": []}))
    return tmp_path


@pytest.fixture(autouse=True)
def _no_real_llm(monkeypatch):
    monkeypatch.setattr("app.ai.orchestrator._provider", lambda: None)


@pytest.fixture(autouse=True)
def _fresh_analytics_cache(monkeypatch):
    from app.analytics.cache import reset_cache
    from app.live.cache import InMemoryCache

    monkeypatch.setattr("app.analytics.cache.build_cache", lambda _url: (InMemoryCache(), False))
    reset_cache()
    yield
    reset_cache()
