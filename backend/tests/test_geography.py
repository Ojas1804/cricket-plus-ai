import json

import pytest
from sqlalchemy import select

from app.analytics.query_dsl import AnalyticsQuery
from app.analytics.query_executor import execute_query
from app.cricket.ingestion.cricsheet import ingest_path
from app.cricket.models import Team, Venue
from app.cricket.normalization.geography import backfill_geography, infer_venue_country, team_country
from tests.conftest import _d


def intl(venue, city, date, india_runs, aus_runs):
    return {
        "info": {"dates": [date], "match_type": "IT20", "season": date[:4], "team_type": "international",
                 "teams": ["India", "Australia"], "venue": venue, "city": city, "outcome": {"winner": "India"}},
        "innings": [
            {"team": "India", "overs": [{"over": 0, "deliveries": [_d("A Bat", "B Bowl", india_runs)]}]},
            {"team": "Australia", "overs": [{"over": 0, "deliveries": [_d("B Bat", "A Bowl", aus_runs)]}]},
        ],
    }


@pytest.fixture
def intl_db(session, tmp_path):
    (tmp_path / "2001.json").write_text(json.dumps(intl("Melbourne Cricket Ground", "Melbourne", "2023-01-01", 10, 20)))
    (tmp_path / "2002.json").write_text(json.dumps(intl("Wankhede Stadium", "Mumbai", "2023-02-01", 30, 5)))
    (tmp_path / "2003.json").write_text(json.dumps(intl("Mystery Ground", "Nowhere", "2023-03-01", 7, 7)))
    ingest_path(session, tmp_path)
    return session


def q(**kw):
    return AnalyticsQuery(**{"dataset": "batting_performances", "metrics": ["runs"], **kw})


def by_player(res, name, key):
    return {r[key]: r["runs"] for r in res.rows if r["player"] == name}


def test_geography_inference():
    assert infer_venue_country("Melbourne", "Melbourne Cricket Ground") == "Australia"
    assert infer_venue_country(None, "Sharjah Cricket Stadium") == "United Arab Emirates"
    assert infer_venue_country("Nowhere", "Mystery Ground") is None
    assert team_country("India Women", "international") == "India"
    assert team_country("Mumbai Indians", "club") is None


def test_ingestion_populates_countries(intl_db):
    assert intl_db.scalar(select(Venue.country).where(Venue.city == "Mumbai")) == "India"
    assert intl_db.scalar(select(Team.country).where(Team.name == "Australia")) == "Australia"


def test_home_away_split(intl_db):
    res = execute_query(intl_db, q(groupBy=["player_id", "home_away"]))
    assert by_player(res, "A Bat", "home_away") == {"home": 30, "away": 10, None: 7}
    assert by_player(res, "B Bat", "home_away") == {"home": 20, "away": 5, None: 7}
    assert "home_away" in res.provenance["definitions"]
    assert any("1 matches" in w for w in res.provenance["warnings"])


def test_home_filter(intl_db):
    res = execute_query(intl_db, q(filters=[{"field": "home_away", "operator": "equals", "value": "home"}]))
    assert {r["player"]: r["runs"] for r in res.rows} == {"A Bat": 30, "B Bat": 20}


def test_opposition_and_venue_country_splits(intl_db):
    res = execute_query(intl_db, q(groupBy=["player_id", "opposition"], filters=[{"field": "player", "operator": "equals", "value": "A Bat"}]))
    assert by_player(res, "A Bat", "opposition") == {"Australia": 47}
    res = execute_query(intl_db, q(groupBy=["player_id", "venue_country"], filters=[{"field": "player", "operator": "equals", "value": "A Bat"}]))
    assert by_player(res, "A Bat", "venue_country") == {"Australia": 10, "India": 30, None: 7}
    res = execute_query(intl_db, q(filters=[{"field": "venue_country", "operator": "equals", "value": "Australia"}]))
    assert {r["player"]: r["runs"] for r in res.rows} == {"A Bat": 10, "B Bat": 20}


def test_bowling_home_away_uses_bowlers_team(intl_db):
    res = execute_query(intl_db, AnalyticsQuery(dataset="bowling_performances", metrics=["runs_conceded"],
                                                groupBy=["player_id", "home_away"], filters=[{"field": "home_away", "operator": "equals", "value": "home"}]))
    assert {r["player"]: r["runs_conceded"] for r in res.rows} == {"B Bowl": 10, "A Bowl": 5}


def test_invalid_home_away_value():
    with pytest.raises(ValueError):
        q(filters=[{"field": "home_away", "operator": "equals", "value": "neutral"}])


def test_backfill(session):
    from app.cricket.models import Team as T, Venue as V
    session.add_all([V(name="Eden Gardens", city="Kolkata"), T(name="India", team_type="international")])
    session.commit()
    assert backfill_geography(session) == (1, 1)
    assert session.scalar(select(V.country)) == "India"
