import pytest
from pydantic import ValidationError

from app.analytics.query_dsl import AnalyticsQuery
from app.analytics.query_executor import execute_query
from app.cricket.ingestion.cricsheet import ingest_path


@pytest.fixture
def loaded(session, match_dir):
    ingest_path(session, match_dir)
    return session


def q(**kw):
    return AnalyticsQuery(**{"dataset": "batting_performances", "metrics": ["runs"], **kw})


def test_batting_leaderboard(loaded):
    res = execute_query(loaded, q(metrics=["runs", "balls_faced", "dismissals", "batting_average", "strike_rate"],
                                  orderBy=[{"field": "runs", "direction": "desc"}]))
    assert [r["player"] for r in res.rows] == ["P2", "P1"]
    p2 = res.rows[0]
    assert (p2["runs"], p2["balls_faced"], p2["dismissals"], p2["batting_average"], p2["strike_rate"]) == (8, 8, 1, 8.0, 100.0)
    assert res.provenance["coverage"]["matches"] == 1
    assert "batting_average" in res.provenance["definitions"]


def test_bowling_metrics(loaded):
    res = execute_query(loaded, AnalyticsQuery(dataset="bowling_performances",
                        metrics=["wickets", "economy", "bowling_average", "maidens"], orderBy=[{"field": "wickets"}]))
    z = next(r for r in res.rows if r["player"] == "Z")
    assert (z["wickets"], z["economy"], z["bowling_average"]) == (1, 18.0, 15.0)
    y = next(r for r in res.rows if r["player"] == "Y")
    assert (y["economy"], y["bowling_average"], y["maidens"]) == (0.0, None, 1)


def test_filters(loaded):
    assert len(execute_query(loaded, q(filters=[{"field": "opposition", "operator": "equals", "value": "Beta"}])).rows) == 2
    assert execute_query(loaded, q(filters=[{"field": "opposition", "operator": "equals", "value": "Alpha"}])).rows == []
    assert len(execute_query(loaded, q(filters=[{"field": "match_date", "operator": "gte", "value": "2024-01-01"}])).rows) == 2
    r = execute_query(loaded, q(filters=[{"field": "match_date", "operator": "lt", "value": "2024-01-01"}]))
    assert r.rows == [] and r.provenance["warnings"]


def test_metric_threshold_filter_and_limit(loaded):
    res = execute_query(loaded, q(filters=[{"field": "runs", "operator": "gte", "value": 6}], limit=1))
    assert [r["player"] for r in res.rows] == ["P2"]


def test_group_by_season(loaded):
    res = execute_query(loaded, q(groupBy=["player_id", "season"]))
    assert {r["season"] for r in res.rows} == {"2024"}


def test_venue_country_warning(loaded):
    res = execute_query(loaded, q(filters=[{"field": "venue_country", "operator": "equals", "value": "Australia"}]))
    assert res.rows == [] and any("Venue country" in w for w in res.provenance["warnings"])


def test_sql_injection_value_is_bound(loaded):
    res = execute_query(loaded, q(filters=[{"field": "player", "operator": "equals", "value": "x' OR '1'='1"}]))
    assert res.rows == []


@pytest.mark.parametrize("bad", [
    {"metrics": ["nope"]},
    {"filters": [{"field": "drop_table", "operator": "equals", "value": "x"}]},
    {"filters": [{"field": "format", "operator": "gte", "value": "T20"}]},
    {"filters": [{"field": "match_date", "operator": "gte", "value": "not-a-date"}]},
    {"orderBy": [{"field": "strike_rate_x"}]},
    {"limit": 1000},
    {"groupBy": ["season"]},
])
def test_invalid_dsl_rejected(bad):
    with pytest.raises(ValidationError):
        q(**bad)
