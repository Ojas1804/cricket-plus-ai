import pytest

from app.ai.models import Intent, MentionedEntities
from app.ai.orchestrator import focus_widget, handle_prompt
from app.core.exceptions import ValidationFailure
from app.widgets.schemas import PromptRequest
from tests.test_ai_pipeline import FakeProvider, plan, pq
from tests.test_geography import intl_db  # noqa: F401


def team_intent(*teams):
    return Intent(kind="analytics", summary="s", clarification_question="",
                  entities=MentionedEntities(players=[], teams=list(teams), competitions=[], venues=[]))


def tpq(viz, metrics, filters=(), group_by=("team",), order=(), limit=10):
    return pq(viz, metrics, filters, group_by, dataset="team_results", order=order, limit=limit)


def run(db, provider):
    return handle_prompt(PromptRequest(prompt="x"), db, provider)


def test_team_leaderboard_is_not_player_selectable(intl_db):
    w = run(intl_db, FakeProvider(team_intent(), plan(tpq("leaderboard", ("wins", "win_percentage"), order=("wins",))))).widgets[0]
    assert w.type == "leaderboard" and w.data.columns[:2] == ["rank", "team"]
    assert [r["team"] for r in w.data.rows] == ["India", "Australia"] and not w.interactions.selectableRows
    assert w.query["dsl"]["entity"] == "team"


def test_two_team_comparison_resolves_names(intl_db):
    q = tpq("comparison", ("matches", "wins", "average_score"), [("team", "in", ["india", "AUSTRALIA"])])
    w = run(intl_db, FakeProvider(team_intent("india", "AUSTRALIA"), plan(q))).widgets[0]
    assert w.type == "comparison" and set(w.data.columns) == {"metric", "India", "Australia"}
    assert {r["metric"]: r["India"] for r in w.data.rows} == {"matches": 3, "wins": 3, "average score": 15.67}


def test_team_performance_across_venues_chart_and_head_to_head(intl_db):
    q = tpq("chart", ("runs_scored",), [("team", "equals", "India")], ("team", "venue"))
    w = run(intl_db, FakeProvider(team_intent("India"), plan(q))).widgets[0]
    assert w.type == "chart" and w.data.extra["series"][0]["name"] == "India"
    assert set(w.data.extra["categories"]) == {"Melbourne Cricket Ground", "Wankhede Stadium", "Mystery Ground"}

    h2h = tpq("table", ("matches", "wins"), [("team", "equals", "India"), ("opposition", "equals", "Australia")], ("team", "opposition"))
    w = run(intl_db, FakeProvider(team_intent("India", "Australia"), plan(h2h))).widgets[0]
    assert w.data.rows == [{"team": "India", "opposition": "Australia", "matches": 3, "wins": 3}]


def test_team_widget_cannot_follow_player_selection(intl_db):
    w = run(intl_db, FakeProvider(team_intent(), plan(tpq("table", ("wins",))))).widgets[0]
    with pytest.raises(ValidationFailure):
        focus_widget(intl_db, w.id, 1)


def test_player_filter_on_team_dataset_triggers_repair(intl_db):
    bad = tpq("table", ("wins",), [("player_id", "equals", "1")])
    prov = FakeProvider(team_intent(), plan(bad), plan(tpq("table", ("wins",))))
    assert run(intl_db, prov).widgets[0].type == "table"
    assert "rejected by validation" in prov.prompts[-1][1]


def _chart(chart_type, metrics, group_by, filters=()):
    q = tpq("chart", metrics, filters, group_by)
    q.chart_type = chart_type
    return q


def test_radar_chart_for_team_profiles(intl_db):
    w = run(intl_db, FakeProvider(team_intent(), plan(_chart("radar", ("wins", "runs_scored", "average_score"), ("team",))))).widgets[0]
    x = w.data.extra
    assert x["chartType"] == "radar" and [i["name"] for i in x["indicators"]] == ["wins", "runs scored", "average score"]
    assert {s["name"]: s["value"] for s in x["radarSeries"]}["India"] == [3, 47, 15.67]
    assert all(i["max"] > 0 for i in x["indicators"])


def test_radar_falls_back_to_bar_with_too_few_metrics_or_splits(intl_db):
    w = run(intl_db, FakeProvider(team_intent(), plan(_chart("radar", ("wins",), ("team",))))).widgets[0]
    assert w.data.extra["chartType"] == "bar"
    w = run(intl_db, FakeProvider(team_intent(), plan(_chart("radar", ("wins", "matches", "losses"), ("team", "season"))))).widgets[0]
    assert w.data.extra["chartType"] == "bar"


def test_heatmap_one_entity_two_splits_and_single_split(intl_db):
    f = [("team", "equals", "India")]
    w = run(intl_db, FakeProvider(team_intent("India"), plan(_chart("heatmap", ("runs_scored",), ("team", "opposition", "venue"), f)))).widgets[0]
    x = w.data.extra
    assert x["chartType"] == "heatmap" and x["xCategories"] == ["Australia"] and len(x["yCategories"]) == 3
    assert sorted(c[2] for c in x["cells"]) == [7, 10, 30] and x["min"] == 7 and x["max"] == 30

    w = run(intl_db, FakeProvider(team_intent(), plan(_chart("heatmap", ("win_percentage",), ("team", "opposition"))))).widgets[0]
    x = w.data.extra
    assert x["chartType"] == "heatmap" and set(x["yCategories"]) == {"India", "Australia"} and x["xCategories"] == ["Australia", "India"]
    assert {(x["yCategories"][c[1]], x["xCategories"][c[0]]): c[2] for c in x["cells"]}[("India", "Australia")] == 100.0


def test_heatmap_with_many_entities_and_two_splits_falls_back(intl_db):
    w = run(intl_db, FakeProvider(team_intent(), plan(_chart("heatmap", ("wins",), ("team", "opposition", "season"))))).widgets[0]
    assert w.data.extra["chartType"] == "bar"
