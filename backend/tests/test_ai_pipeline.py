import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.entity_resolver import AmbiguousEntity, UnknownEntity, resolve_competition, resolve_player
from app.ai.models import Intent, MentionedEntities, PlannedFilter, PlannedOrder, PlannedQuery, QueryPlan
from app.ai.orchestrator import handle_prompt, refresh_widget
from app.cricket.ingestion.cricsheet import ingest_path
from app.cricket.models import BattingPerformance, Player
from app.widgets.schemas import PromptRequest


class FakeProvider:
    def __init__(self, *responses, text="A strike rate is runs per 100 balls."):
        self.responses, self.prompts, self._text = list(responses), [], text

    def parse(self, system, user, schema):
        self.prompts.append((schema.__name__, user))
        out = next(r for r in self.responses if isinstance(r, schema))
        self.responses.remove(out)
        return out

    def text(self, system, user):
        return self._text


def intent(kind="analytics", players=(), question=""):
    return Intent(kind=kind, summary="s", entities=MentionedEntities(players=list(players), teams=[], competitions=[], venues=[]),
                  clarification_question=question)


def pq(viz="leaderboard", metrics=("runs",), filters=(), group_by=("player_id",), dataset="batting_performances", order=("runs",), limit=10):
    return PlannedQuery(
        title="T", description="D", visualization=viz, chart_type="line", dataset=dataset,
        filters=[PlannedFilter(field=f, operator=o, value=v) for f, o, v in filters], metrics=list(metrics),
        group_by=list(group_by), order_by=[PlannedOrder(field=f, direction="desc") for f in order], limit=limit)


def plan(*queries, reason=""):
    return QueryPlan(queries=list(queries), unanswerable_reason=reason)


@pytest.fixture
def db(session, match_dir):
    ingest_path(session, match_dir)
    return session


def run(db, prompt, provider, action="ADD", target=None):
    return handle_prompt(PromptRequest(prompt=prompt, action=action, targetWidgetId=target), db, provider)


def test_leaderboard_end_to_end(db):
    res = run(db, "top run scorers", FakeProvider(intent(), plan(pq())))
    w = res.widgets[0]
    assert res.status == "COMPLETED" and w.type == "leaderboard"
    assert [r["player"] for r in w.data.rows] == ["P2", "P1"] and w.data.rows[0]["rank"] == 1
    assert w.metadata.provenance["source"] == "internal_analytics" and not w.metadata.isMock
    assert w.query["dsl"]["dataset"] == "batting_performances" and w.interactions.selectableRows


def test_comparison_and_trend_from_one_prompt(db):
    p = plan(pq("comparison", ("runs", "strike_rate"), [("player", "in", ["P1", "P2"])], order=()),
             pq("chart", ("runs",), [("player", "in", ["P1", "P2"])], ("player_id", "season"), order=()))
    res = run(db, "compare P1 and P2 with trend", FakeProvider(intent(players=["P1", "P2"]), p))
    cmp_, chart = res.widgets
    assert cmp_.data.columns == ["metric", "P1", "P2"] and cmp_.data.rows[0] == {"metric": "runs", "P1": 5, "P2": 8}
    assert chart.type == "chart" and chart.data.extra["categories"] == ["2024"]
    assert {s["name"] for s in chart.data.extra["series"]} == {"P1", "P2"}


def test_ambiguous_player_asks_for_clarification(db):
    db.add_all([Player(full_name="RG Sharma", display_name="RG Sharma"), Player(full_name="RA Sharma", display_name="RA Sharma")])
    db.commit()
    res = run(db, "Sharma runs", FakeProvider(intent(players=["Sharma"])))
    assert res.status == "CLARIFICATION_REQUIRED" and set(res.options) == {"RG Sharma", "RA Sharma"} and not res.widgets


def test_unknown_player_is_reported(db):
    res = run(db, "x", FakeProvider(intent(players=["Nobody Here"])))
    assert res.status == "CLARIFICATION_REQUIRED" and "Nobody Here" in res.message


def test_update_preserves_id_and_modifies_query(db):
    first = run(db, "top", FakeProvider(intent(), plan(pq()))).widgets[0]
    prov = FakeProvider(intent(), plan(pq(filters=[("runs", "gte", "6")])))
    res = run(db, "only 6+ runs", prov, "UPDATE", first.id)
    upd = res.widgets[0]
    assert upd.id == first.id and [r["player"] for r in upd.data.rows] == ["P2"]
    assert '"dsl"' in prov.prompts[0][1] and '"dsl"' in prov.prompts[1][1]


def test_invalid_plan_is_repaired_once(db):
    prov = FakeProvider(intent(), plan(pq(metrics=("bogus",))), plan(pq()))
    res = run(db, "top", prov)
    assert res.widgets[0].type == "leaderboard" and sum(1 for n, _ in prov.prompts if n == "QueryPlan") == 2
    assert "rejected by validation" in prov.prompts[-1][1]


def test_persistently_invalid_plan_degrades_to_clarification(db):
    res = run(db, "top", FakeProvider(intent(), plan(pq(metrics=("bogus",))), plan(pq(metrics=("bogus",)))))
    assert res.status == "CLARIFICATION_REQUIRED"


def test_unanswerable_and_unsupported(db):
    res = run(db, "x", FakeProvider(intent(), plan(reason="No fielding data is available.")))
    assert res.status == "CLARIFICATION_REQUIRED" and "fielding" in res.message
    res = run(db, "weather?", FakeProvider(intent(kind="unsupported")))
    assert res.status == "CLARIFICATION_REQUIRED"


def test_explain_is_labelled_as_ai_generated(db):
    w = run(db, "what is strike rate", FakeProvider(intent(kind="explain"))).widgets[0]
    assert w.type == "text" and w.metadata.source == "llm_explanation" and w.metadata.provenance["warnings"]


def test_no_data_message(session):
    w = run(session, "top", FakeProvider(intent(), plan(pq()))).widgets[0]
    assert w.type == "text" and "ingest" in w.data.extra["text"]


def test_refresh_reexecutes_stored_query(db):
    w = run(db, "top", FakeProvider(intent(), plan(pq()))).widgets[0]
    p1 = db.scalar(select(Player).where(Player.display_name == "P1"))
    db.scalar(select(BattingPerformance).where(BattingPerformance.player_id == p1.id)).runs = 100
    db.commit()
    from app.widgets.service import widget_service
    refreshed = refresh_widget(db, w.id)
    assert refreshed.id == w.id and widget_service.get(w.id).data.rows[0]["player"] == "P1"


def test_player_name_forms(session):
    session.add_all([Player(full_name="V Kohli", display_name="V Kohli"), Player(full_name="SPD Smith", display_name="SPD Smith"),
                     Player(full_name="RG Sharma", display_name="RG Sharma"), Player(full_name="RA Sharma", display_name="RA Sharma")])
    session.commit()
    assert resolve_player(session, "Virat Kohli").label == "V Kohli"
    assert resolve_player(session, "v kohli").label == "V Kohli"
    assert resolve_player(session, "Steve Smith").label == "SPD Smith"
    with pytest.raises(AmbiguousEntity):
        resolve_player(session, "Rohit Sharma")
    with pytest.raises(UnknownEntity):
        resolve_player(session, "Virat Singh")


def test_competition_acronym(db):
    assert resolve_competition(db, "Test League").label == "Test League"
    from app.cricket.models import Competition
    db.add(Competition(name="Indian Premier League", format="T20", competition_type="league"))
    db.commit()
    assert resolve_competition(db, "IPL").label == "Indian Premier League"


def _chart_pq(chart_type, metrics, group_by=("player_id",)):
    q = pq("chart", metrics, [], group_by, order=())
    q.chart_type = chart_type
    return q


def test_scatter_and_pie_charts(db):
    sc = run(db, "x", FakeProvider(intent(), plan(_chart_pq("scatter", ("runs", "strike_rate"))))).widgets[0]
    assert sc.data.extra["chartType"] == "scatter" and {p["name"] for p in sc.data.extra["points"]} == {"P1", "P2"}
    pie = run(db, "x", FakeProvider(intent(), plan(_chart_pq("pie", ("runs",))))).widgets[0]
    assert {s["name"]: s["value"] for s in pie.data.extra["slices"]} == {"P1": 5, "P2": 8}
    bar = run(db, "x", FakeProvider(intent(), plan(_chart_pq("scatter", ("runs",))))).widgets[0]
    assert bar.data.extra["chartType"] == "bar"


def test_focus_retargets_player_filter_only(db):
    from app.ai.orchestrator import focus_widget
    from app.core.exceptions import ValidationFailure

    p1 = db.scalar(select(Player).where(Player.display_name == "P1"))
    p2 = db.scalar(select(Player).where(Player.display_name == "P2"))
    chart_q = pq("chart", ("runs",), [("player", "equals", "P1"), ("season", "equals", "2024")], ("player_id", "season"), order=())
    chart_q.title = "P1 runs by season"
    w = run(db, "x", FakeProvider(intent(players=["P1"]), plan(chart_q))).widgets[0]
    out = focus_widget(db, w.id, p2.id)
    assert out.id == w.id and out.title == "P2 runs by season"
    filters = {f["field"]: f["value"] for f in out.query["dsl"]["filters"]}
    assert filters == {"season": "2024", "player_id": p2.id}
    assert out.data.extra["series"][0]["name"] == "P2"

    lb = run(db, "x", FakeProvider(intent(), plan(pq()))).widgets[0]
    with pytest.raises(ValidationFailure):
        focus_widget(db, lb.id, p1.id)
