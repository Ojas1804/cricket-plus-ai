"""Team-level analytics: one row per (match, team) is built first, then aggregated. Parameterized SQLAlchemy only."""
from sqlalchemy import and_, case, distinct, func, literal_column, null, select
from sqlalchemy.orm import Session, aliased

from app.analytics.metrics import cricket_metrics as m
from app.analytics.query_dsl import METRICS, AnalyticsQuery
from app.analytics.query_executor import (
    _CMP, GEO_FIELDS, QueryResult, _sum, _where, assemble_provenance, geo_fields_used,
)
from app.cricket.models import Competition, Innings, Match, Team, Venue

FILTERABLE = ("team", "opposition", "season", "format", "competition", "venue", "venue_country", "home_away", "match_date")


def _inn_sum(expr, side_col, tm):
    return select(func.coalesce(expr, 0)).where(Innings.match_id == Match.id, side_col == tm.id).scalar_subquery()


def _team_match_rows():
    tm, opp = aliased(Team), aliased(Team)
    opp_id = case((tm.id == Match.team_1_id, Match.team_2_id), else_=Match.team_1_id)
    home_away = case(
        (Venue.country.is_(None) | tm.country.is_(None), null()),
        (Venue.country == tm.country, literal_column("'home'")),
        else_=literal_column("'away'"))
    bat, bowl = Innings.batting_team_id, Innings.bowling_team_id
    stmt = (select(
        Match.id.label("match_id"), tm.name.label("team"), opp.name.label("opposition"), Match.season.label("season"),
        Match.format.label("format"), Competition.name.label("competition"), Venue.name.label("venue"),
        Venue.country.label("venue_country"), home_away.label("home_away"), Match.start_time.label("match_date"),
        case((Match.winner_id == tm.id, 1), else_=0).label("is_win"),
        case((and_(Match.winner_id.is_not(None), Match.winner_id != tm.id), 1), else_=0).label("is_loss"),
        case((Match.winner_id.is_(None), 1), else_=0).label("is_none"),
        _inn_sum(func.sum(Innings.runs), bat, tm).label("runs_for"),
        _inn_sum(func.sum(Innings.legal_balls), bat, tm).label("balls_for"),
        _inn_sum(func.sum(Innings.wickets), bat, tm).label("wkts_lost"),
        _inn_sum(func.count(Innings.id), bat, tm).label("inn_bat"),
        _inn_sum(func.sum(Innings.runs), bowl, tm).label("runs_against"),
        _inn_sum(func.sum(Innings.legal_balls), bowl, tm).label("balls_against"),
        _inn_sum(func.sum(Innings.wickets), bowl, tm).label("wkts_taken"),
        _inn_sum(func.count(Innings.id), bowl, tm).label("inn_bowl"))
        .select_from(Match)
        .join(tm, (tm.id == Match.team_1_id) | (tm.id == Match.team_2_id)).join(opp, opp.id == opp_id)
        .outerjoin(Venue, Venue.id == Match.venue_id).outerjoin(Competition, Competition.id == Match.competition_id))
    return stmt.subquery()


def _derive(r: dict) -> dict:
    r["win_percentage"] = m.win_percentage(r["wins"], r["matches"])
    r["average_score"] = m.average_per_innings(r["runs_scored"], r["innings_batted"])
    r["average_conceded"] = m.average_per_innings(r["runs_conceded"], r["innings_bowled"])
    r["run_rate"] = m.run_rate(r["runs_scored"], r["_balls_for"])
    r["run_rate_conceded"] = m.run_rate(r["runs_conceded"], r["_balls_against"])
    return r


def execute_team_query(session: Session, query: AnalyticsQuery) -> QueryResult:
    t = _team_match_rows()
    columns = {k: t.c[k] for k in FILTERABLE}
    conditions = [_where(columns, f) for f in query.filters if f.field in columns]
    metric_filters = [f for f in query.filters if f.field in METRICS[query.dataset]]

    aggs = {
        "matches": func.count(), "wins": _sum(t.c.is_win), "losses": _sum(t.c.is_loss), "no_results": _sum(t.c.is_none),
        "runs_scored": _sum(t.c.runs_for), "runs_conceded": _sum(t.c.runs_against), "innings_batted": _sum(t.c.inn_bat),
        "innings_bowled": _sum(t.c.inn_bowl), "wickets_lost": _sum(t.c.wkts_lost), "wickets_taken": _sum(t.c.wkts_taken),
        "_balls_for": _sum(t.c.balls_for), "_balls_against": _sum(t.c.balls_against),
    }
    stmt = (select(*[columns[g].label(g) for g in query.groupBy], *[e.label(k) for k, e in aggs.items()])
            .where(*conditions).group_by(*[columns[g] for g in query.groupBy]))
    rows = [_derive(dict(r._mapping)) for r in session.execute(stmt)]

    for f in metric_filters:
        rows = [r for r in rows if r[f.field] is not None and _CMP[f.operator](r[f.field], f.value)]
    for o in reversed(query.orderBy or []):
        present = [r for r in rows if r[o.field] is not None]
        missing = [r for r in rows if r[o.field] is None]
        rows = sorted(present, key=lambda r: r[o.field], reverse=o.direction == "desc") + missing
    total = len(rows)
    out_cols = [*dict.fromkeys([*query.groupBy, *query.metrics])]
    rows = [{c: r.get(c) for c in out_cols} for r in rows[: query.limit]]

    cov = session.execute(
        select(func.count(distinct(t.c.match_id)), func.min(t.c.match_date), func.max(t.c.match_date)).where(*conditions)).one()
    geo_used = geo_fields_used(query)
    unknown = 0
    if geo_used:
        non_geo = [_where(columns, f) for f in query.filters if f.field in columns and f.field not in GEO_FIELDS]
        unknown_cond = columns["home_away"].is_(None) if "home_away" in geo_used else columns["venue_country"].is_(None)
        unknown = session.scalar(select(func.count(distinct(t.c.match_id))).where(*non_geo, unknown_cond)) or 0
    return QueryResult(columns=out_cols, rows=rows, provenance=assemble_provenance(session, query, cov, total, unknown, geo_used))
