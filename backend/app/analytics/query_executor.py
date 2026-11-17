"""Executes validated DSL queries via parameterized SQLAlchemy. No LLM-provided SQL ever reaches the database."""
from datetime import date, datetime, timezone
from typing import Any

from pydantic import BaseModel
from sqlalchemy import Select, case, distinct, func, literal_column, null, select
from sqlalchemy.orm import Session, aliased

from app.analytics.metrics import cricket_metrics as m
from app.analytics.query_dsl import AnalyticsQuery, Filter, METRICS
from app.cricket.models import (
    BattingPerformance, BowlingPerformance, Competition, DataIngestionLog, Innings, Match, Player, Team, Venue,
)

DEFINITIONS = {
    "batting_average": "runs / dismissals (undefined when never dismissed; retired hurt is not a dismissal)",
    "strike_rate": "runs / balls faced * 100 (wides are not balls faced; no-balls are)",
    "economy": "runs conceded / legal balls * 6 (byes, leg byes and penalty runs are not charged to the bowler)",
    "bowling_average": "runs conceded / wickets credited to the bowler (run outs and retirements excluded)",
    "bowling_strike_rate": "legal balls / wickets credited to the bowler",
    "home_away": "home = venue country equals the team's (or the player's national team's) country; anything else (including neutral "
                 "venues) = away. Unknown for club/franchise teams and venues whose country could not be determined.",
    "win_percentage": "wins / matches * 100; draws, ties without a winner and no-results count as matches but not wins",
    "no_results": "matches with no recorded winner (draws, ties without a result, abandoned matches)",
    "average_score": "runs scored / innings batted (all-out and declared innings alike)",
    "average_conceded": "runs conceded / innings bowled",
    "run_rate": "runs scored / legal balls faced * 6",
    "run_rate_conceded": "runs conceded / legal balls bowled * 6",
}
GEO_FIELDS = ("venue_country", "home_away")
FILTER_NOTE = "Aggregate-metric filters are applied after aggregation (HAVING semantics)."


class QueryResult(BaseModel):
    columns: list[str]
    rows: list[dict[str, Any]]
    provenance: dict[str, Any]


def _sum(expr) -> Any:
    return func.coalesce(func.sum(expr), 0)


def _flag(cond) -> Any:
    return case((cond, 1), else_=0)


def _build(session_query: AnalyticsQuery):
    batting = session_query.dataset == "batting_performances"
    Perf = BattingPerformance if batting else BowlingPerformance
    bat_team, opp_team = (Innings.batting_team_id, Innings.bowling_team_id) if batting else (Innings.bowling_team_id, Innings.batting_team_id)
    team, opp = aliased(Team), aliased(Team)

    home_away = case(
        (Venue.country.is_(None) | team.country.is_(None), null()),
        (Venue.country == team.country, literal_column("'home'")),
        else_=literal_column("'away'"))
    columns = {
        "home_away": home_away, "player_id": Player.id, "season": Match.season, "format": Match.format,
        "competition": Competition.name, "team": team.name, "opposition": opp.name, "venue": Venue.name,
        "venue_country": Venue.country, "player": Player.display_name, "match_date": Match.start_time,
    }
    if batting:
        aggs = {
            "matches": func.count(distinct(Perf.match_id)), "innings": func.count(Perf.id),
            "runs": _sum(Perf.runs), "balls_faced": _sum(Perf.balls_faced), "fours": _sum(Perf.fours),
            "sixes": _sum(Perf.sixes), "dismissals": _sum(_flag(Perf.is_dismissed)),
            "fifties": _sum(_flag((Perf.runs >= 50) & (Perf.runs < 100))), "hundreds": _sum(_flag(Perf.runs >= 100)),
        }
    else:
        aggs = {
            "matches": func.count(distinct(Perf.match_id)), "innings": func.count(Perf.id),
            "balls_bowled": _sum(Perf.balls_bowled), "runs_conceded": _sum(Perf.runs_conceded),
            "wickets": _sum(Perf.wickets), "maidens": _sum(Perf.maidens),
        }

    def joined(stmt: Select) -> Select:
        return (stmt.select_from(Perf)
                .join(Innings, Innings.id == Perf.innings_id).join(Match, Match.id == Innings.match_id)
                .join(Player, Player.id == Perf.player_id)
                .join(team, team.id == bat_team).join(opp, opp.id == opp_team)
                .outerjoin(Venue, Venue.id == Match.venue_id).outerjoin(Competition, Competition.id == Match.competition_id))

    return Perf, columns, aggs, joined


def _where(columns: dict, f: Filter):
    col, v = columns[f.field], f.value
    if f.field == "match_date":
        v = date.fromisoformat(v)  # type: ignore[arg-type]
    if f.field == "player_id" and not isinstance(v, list):
        v = int(v)
    return {"equals": lambda: col == v, "in": lambda: col.in_(v), "gte": lambda: col >= v,
            "lte": lambda: col <= v, "gt": lambda: col > v, "lt": lambda: col < v}[f.operator]()


def _derive(row: dict, batting: bool) -> dict:
    if batting:
        row["not_outs"] = row["innings"] - row["dismissals"]
        row["batting_average"] = m.batting_average(row["runs"], row["dismissals"])
        row["strike_rate"] = m.batting_strike_rate(row["runs"], row["balls_faced"])
    else:
        row["economy"] = m.bowling_economy(row["runs_conceded"], row["balls_bowled"])
        row["bowling_average"] = m.bowling_average(row["runs_conceded"], row["wickets"])
        row["bowling_strike_rate"] = m.bowling_strike_rate(row["balls_bowled"], row["wickets"])
    return row


_CMP = {"equals": lambda a, b: a == b, "gte": lambda a, b: a >= b, "lte": lambda a, b: a <= b,
        "gt": lambda a, b: a > b, "lt": lambda a, b: a < b}


def execute_query(session: Session, query: AnalyticsQuery) -> QueryResult:
    if query.dataset == "team_results":
        from app.analytics.team_executor import execute_team_query

        return execute_team_query(session, query)
    batting = query.dataset == "batting_performances"
    _, columns, aggs, joined = _build(query)
    metric_names = METRICS[query.dataset]
    row_filters = [f for f in query.filters if f.field in columns]
    metric_filters = [f for f in query.filters if f.field in metric_names]
    conditions = [_where(columns, f) for f in row_filters]

    group_cols = [columns[g].label(g) for g in query.groupBy]
    stmt = joined(select(*group_cols, Player.display_name.label("player"), *[e.label(k) for k, e in aggs.items()]))
    stmt = stmt.where(*conditions).group_by(*[columns[g] for g in query.groupBy], Player.display_name)

    rows = [_derive(dict(r._mapping), batting) for r in session.execute(stmt)]
    for f in metric_filters:
        rows = [r for r in rows if r[f.field] is not None and _CMP[f.operator](r[f.field], f.value)]
    for o in reversed(query.orderBy or []):
        present = [r for r in rows if r[o.field] is not None]
        missing = [r for r in rows if r[o.field] is None]
        rows = sorted(present, key=lambda r: r[o.field], reverse=o.direction == "desc") + missing
    total = len(rows)
    rows = rows[: query.limit]

    out_cols = [*dict.fromkeys(["player", *query.groupBy, *query.metrics])]
    rows = [{c: r.get(c) for c in out_cols} for r in rows]
    return QueryResult(columns=out_cols, rows=rows, provenance=_provenance(session, query, columns, joined, conditions, total))


def _provenance(session, query, columns, joined, conditions, total) -> dict[str, Any]:
    cov = session.execute(
        joined(select(func.count(distinct(Match.id)), func.min(Match.start_time), func.max(Match.start_time))).where(*conditions)
    ).one()
    geo_used = geo_fields_used(query)
    unknown = 0
    if geo_used:
        non_geo = [_where(columns, f) for f in query.filters if f.field in columns and f.field not in GEO_FIELDS]
        unknown_cond = columns["home_away"].is_(None) if "home_away" in geo_used else Venue.country.is_(None)
        unknown = session.scalar(joined(select(func.count(distinct(Match.id)))).where(*non_geo, unknown_cond)) or 0
    return assemble_provenance(session, query, cov, total, unknown, geo_used)


def geo_fields_used(query: AnalyticsQuery) -> list[str]:
    return [f.field for f in query.filters if f.field in GEO_FIELDS] + [g for g in query.groupBy if g in GEO_FIELDS]


def assemble_provenance(session, query, cov, total, unknown, geo_used) -> dict[str, Any]:
    last = session.scalar(select(func.max(DataIngestionLog.ingested_at)))
    warnings = []
    if not cov[0]:
        warnings.append("No matches in the ingested dataset match these filters; an empty result does not imply no such matches exist.")
    if unknown:
        warnings.append(f"{unknown} matches in scope have an unknown venue country"
                        + (" or a club/franchise team with no home country" if "home_away" in geo_used else "")
                        + " and are not classified.")
    if any(f.field == "venue_country" for f in query.filters):
        known = session.scalar(select(func.count()).select_from(Venue).where(Venue.country.is_not(None)))
        if not known:
            warnings.append("Venue country is not available in the ingested data; venue_country filters cannot match.")
    return {
        "source": "internal_analytics", "dataset": query.dataset, "providers": ["cricsheet"],
        "filters": [f.model_dump() for f in query.filters],
        "coverage": {"matches": cov[0], "earliestMatch": cov[1].isoformat() if cov[1] else None,
                     "latestMatch": cov[2].isoformat() if cov[2] else None, "resultGroups": total},
        "definitions": {k: v for k, v in DEFINITIONS.items() if k in query.metrics or k in geo_used},
        "notes": [FILTER_NOTE] if any(f.field in METRICS[query.dataset] for f in query.filters) else [],
        "warnings": warnings,
        "lastIngestion": last.isoformat() if last else None,
        "executedAt": datetime.now(timezone.utc).isoformat(),
    }
