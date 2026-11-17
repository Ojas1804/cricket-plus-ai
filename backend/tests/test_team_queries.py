import pytest
from pydantic import ValidationError

from app.analytics.query_dsl import AnalyticsQuery
from app.analytics.query_executor import execute_query
from tests.test_geography import intl_db  # noqa: F401  (fixture)

ALL = ["matches", "wins", "losses", "no_results", "win_percentage", "runs_scored", "runs_conceded", "average_score",
       "average_conceded", "run_rate", "wickets_lost"]


def tq(**kw):
    return AnalyticsQuery(**{"dataset": "team_results", "metrics": ["matches", "wins"], **kw})


def by(res, key="team"):
    return {r[key]: r for r in res.rows}


def test_team_defaults_and_overall_record(intl_db):
    q = tq(metrics=ALL)
    assert q.entity == "team" and q.groupBy == ["team"]
    rows = by(execute_query(intl_db, q))
    india, aus = rows["India"], rows["Australia"]
    assert (india["matches"], india["wins"], india["losses"], india["no_results"], india["win_percentage"]) == (3, 3, 0, 0, 100.0)
    assert (aus["matches"], aus["wins"], aus["losses"], aus["win_percentage"]) == (3, 0, 3, 0.0)
    assert (india["runs_scored"], india["runs_conceded"], india["average_score"], india["average_conceded"]) == (47, 32, 15.67, 10.67)
    assert india["run_rate"] == 94.0 and india["wickets_lost"] == 0


def test_team_filter_by_name_and_opposition(intl_db):
    res = execute_query(intl_db, tq(filters=[{"field": "team", "operator": "equals", "value": "India"}], groupBy=["team", "opposition"]))
    assert [(r["team"], r["opposition"], r["matches"]) for r in res.rows] == [("India", "Australia", 3)]


def test_team_home_away_and_venue_splits(intl_db):
    res = execute_query(intl_db, tq(filters=[{"field": "team", "operator": "equals", "value": "India"}],
                                    groupBy=["team", "home_away"], metrics=["matches", "runs_scored"]))
    got = {r["home_away"]: (r["matches"], r["runs_scored"]) for r in res.rows}
    assert got == {"home": (1, 30), "away": (1, 10), None: (1, 7)}
    assert any("unknown venue country" in w for w in res.provenance["warnings"])
    assert "home_away" in res.provenance["definitions"]

    res = execute_query(intl_db, tq(groupBy=["team", "venue"], filters=[{"field": "team", "operator": "equals", "value": "Australia"}]))
    assert {r["venue"] for r in res.rows} == {"Melbourne Cricket Ground", "Wankhede Stadium", "Mystery Ground"}


def test_team_filters_order_limit_and_threshold(intl_db):
    res = execute_query(intl_db, tq(orderBy=[{"field": "wins", "direction": "desc"}], limit=1))
    assert [r["team"] for r in res.rows] == ["India"]
    res = execute_query(intl_db, tq(filters=[{"field": "win_percentage", "operator": "gte", "value": 50}]))
    assert [r["team"] for r in res.rows] == ["India"]
    res = execute_query(intl_db, tq(filters=[{"field": "season", "operator": "equals", "value": "1999"}]))
    assert res.rows == [] and res.provenance["warnings"]
    res = execute_query(intl_db, tq(filters=[{"field": "match_date", "operator": "gte", "value": "2023-02-01"}]))
    assert by(res)["India"]["matches"] == 2


def test_team_query_injection_is_bound(intl_db):
    assert execute_query(intl_db, tq(filters=[{"field": "team", "operator": "equals", "value": "x' OR '1'='1"}])).rows == []


def test_team_dsl_validation():
    for bad in [
        {"filters": [{"field": "player", "operator": "equals", "value": "x"}]},
        {"groupBy": ["season"]},
        {"metrics": ["batting_average"]},
        {"orderBy": [{"field": "runs"}]},
    ]:
        with pytest.raises(ValidationError):
            tq(**bad)
    with pytest.raises(ValidationError):
        AnalyticsQuery(dataset="batting_performances", entity="team", metrics=["runs"])
