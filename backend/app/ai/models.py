"""LLM-facing structured-output models. No defaults: every field is required for strict structured outputs."""
from typing import Literal

from pydantic import BaseModel


class MentionedEntities(BaseModel):
    players: list[str]
    teams: list[str]
    competitions: list[str]
    venues: list[str]


class Intent(BaseModel):
    kind: Literal["analytics", "explain", "live", "unsupported"]
    summary: str
    entities: MentionedEntities
    clarification_question: str


class PlannedFilter(BaseModel):
    field: str
    operator: Literal["equals", "in", "gte", "lte", "gt", "lt"]
    value: str | list[str]


class PlannedOrder(BaseModel):
    field: str
    direction: Literal["asc", "desc"]


class PlannedQuery(BaseModel):
    title: str
    description: str
    visualization: Literal["leaderboard", "table", "chart", "comparison", "profile"]
    chart_type: Literal["line", "bar", "scatter", "pie", "radar", "heatmap"]
    dataset: Literal["batting_performances", "bowling_performances", "team_results"]
    filters: list[PlannedFilter]
    metrics: list[str]
    group_by: list[Literal["player_id", "season", "format", "opposition", "team", "venue", "venue_country", "home_away", "competition"]]
    order_by: list[PlannedOrder]
    limit: int


class QueryPlan(BaseModel):
    queries: list[PlannedQuery]
    unanswerable_reason: str
