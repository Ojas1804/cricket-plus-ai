import json
from datetime import date
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.ai.entity_resolver import normalize_filter
from app.ai.models import Intent, PlannedQuery, QueryPlan
from app.ai.providers.base import LLMProvider
from app.analytics.query_dsl import BATTING_METRICS, BOWLING_METRICS, TEAM_METRICS, AnalyticsQuery, METRICS

MAX_QUERIES = 4

PLANNER_SYSTEM = f"""You plan analytics queries for a cricket workspace. You output a restricted query specification;
the backend validates and executes it. You never write SQL and never calculate statistics.

Datasets and metrics:
- batting_performances: {", ".join(BATTING_METRICS)}
- bowling_performances: {", ".join(BOWLING_METRICS)}
- team_results: {", ".join(TEAM_METRICS)}  (team records and scoring, one row per team per match; use for questions about teams)

Filters (field: operators): format, competition, season, team, opposition, venue, venue_country, player, player_id: equals|in.
match_date: gte|lte|gt|lt with an ISO date (YYYY-MM-DD). Any metric name can also be used as a filter with gte|lte|gt|lt and a number
(this filters after aggregation, e.g. matches >= 50).
- format values: TEST, ODI, T20I, T20, LIST_A, FIRST_CLASS. T20 means domestic/franchise T20; T20I is international T20.
- season is a string such as "2023" or "2023/24". team is the team the player played for; opposition is the other side.
- Use player_id (as a string of the integer) for players listed in resolved entities; otherwise use names exactly as given.
- team_results: filter teams with team / opposition (canonical names from resolved entities); the player and player_id filters are not
  available. For "India vs Australia" use team=India and opposition=Australia; to compare teams use team in [..] with group_by team.
  home_away is from the team's own perspective.
- Dataset choice: batting_performances for runs/averages/strike rates; bowling_performances for wickets/economy.
- team/opposition semantics are from the player's perspective for both datasets.
group_by must include player_id for player datasets and team for team_results (max 3 fields). Splits: season, format, opposition, team,
venue, venue_country, competition, and home_away
(home vs away from the player's own team; unknown for club teams). For "home and away" or "in country X" questions use home_away /
venue_country; for "against team X" use opposition. order_by fields must be metrics or group_by fields.
limit is 1-100 (default 10 for rankings).

visualization:
- leaderboard: ranked list of players (group_by only player_id, ordered, limited).
- comparison: two or more specific players side by side (group_by only player_id, filter player_id with in).
- chart: trends or distributions; use group_by with season or format for time/split trends. chart_type: line for trends, bar for
  category comparisons, pie for share-of-total of one metric (needs several players), scatter to relate two metrics (e.g. average vs
  strike rate; list the x metric first then the y metric), radar for multi-metric profiles of 2-4 players (3+ metrics, group_by only the
  id field), heatmap for one metric across two splits (e.g. a team's win_percentage by opposition and season; group_by id + the two splits).
- table: tabular detail. profile: a single player's career summary (player datasets only).
One request may need several queries (e.g. a comparison and a trend chart); return up to {MAX_QUERIES}.
If an existing widget query is given, return exactly one query that is that query modified as requested.
If the request cannot be answered with these datasets, return no queries and explain in unanswerable_reason; otherwise leave it empty.
Today's date is {{today}}."""


def _coerce(field: str, operator: str, value: Any, metric_names: tuple[str, ...]) -> Any:
    def one(v: Any) -> Any:
        if field == "player_id":
            return int(v)
        if field in metric_names:
            f = float(v)
            return int(f) if f.is_integer() else f
        return v

    return [one(v) for v in value] if isinstance(value, list) else one(value)


def _to_dsl(session: Session, pq: PlannedQuery) -> tuple[AnalyticsQuery, list[str]]:
    metric_names = METRICS[pq.dataset]
    notes: list[str] = []
    filters = []
    for f in pq.filters:
        field, op, value, n = normalize_filter(session, f.field, f.operator, f.value)
        notes.extend(n)
        filters.append({"field": field, "operator": op, "value": _coerce(field, op, value, metric_names)})
    dsl = AnalyticsQuery(
        dataset=pq.dataset, filters=filters, metrics=list(dict.fromkeys(pq.metrics)), groupBy=pq.group_by or ((["team"] if pq.dataset == "team_results" else ["player_id"])),
        orderBy=[o.model_dump() for o in pq.order_by], limit=min(max(pq.limit, 1), 100) if pq.limit else 10)
    return dsl, notes


def plan_query(provider: LLMProvider, session: Session, prompt: str, intent: Intent, resolved: dict[str, list[dict]],
               existing_query: dict | None = None) -> tuple[QueryPlan, list[tuple[PlannedQuery, AnalyticsQuery, list[str]]]]:
    system = PLANNER_SYSTEM.replace("{today}", date.today().isoformat())
    user = f"Request: {prompt}\nInterpretation: {intent.summary}\nResolved entities (canonical): {json.dumps(resolved)}"
    if existing_query:
        user += f"\nExisting widget query to modify (JSON): {json.dumps(existing_query)}"

    for attempt in range(2):
        plan = provider.parse(system, user, QueryPlan)
        if not plan.queries:
            return plan, []
        try:
            return plan, [(pq, *_to_dsl(session, pq)) for pq in plan.queries[:MAX_QUERIES]]
        except (ValidationError, ValueError) as e:
            if attempt == 1:
                raise
            user += f"\n\nYour previous plan was rejected by validation: {str(e)[:600]}\nReturn a corrected plan."
    raise AssertionError("unreachable")
