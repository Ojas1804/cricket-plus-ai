from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator

BATTING_METRICS = ("matches", "innings", "runs", "balls_faced", "fours", "sixes", "dismissals", "not_outs",
                   "fifties", "hundreds", "batting_average", "strike_rate")
BOWLING_METRICS = ("matches", "innings", "balls_bowled", "runs_conceded", "wickets", "maidens",
                   "economy", "bowling_average", "bowling_strike_rate")
TEAM_METRICS = ("matches", "wins", "losses", "no_results", "win_percentage", "runs_scored", "runs_conceded", "innings_batted",
                "innings_bowled", "wickets_lost", "wickets_taken", "average_score", "average_conceded", "run_rate", "run_rate_conceded")
METRICS = {"batting_performances": BATTING_METRICS, "bowling_performances": BOWLING_METRICS, "team_results": TEAM_METRICS}
PLAYER_ONLY_FIELDS = ("player", "player_id")

TEXT_FIELDS = ("format", "competition", "season", "team", "opposition", "venue", "venue_country", "home_away", "player", "player_id")
ROW_FIELDS = (*TEXT_FIELDS, "match_date")
GroupField = Literal["player_id", "season", "format", "opposition", "team", "venue", "venue_country", "home_away", "competition"]

EQ_OPS = ("equals", "in")
CMP_OPS = ("gte", "lte", "gt", "lt", "equals")

Value = str | int | float | list[str | int | float]


class Filter(BaseModel):
    field: str
    operator: Literal["equals", "in", "gte", "lte", "gt", "lt"]
    value: Value


class OrderBy(BaseModel):
    field: str
    direction: Literal["asc", "desc"] = "desc"


class AnalyticsQuery(BaseModel):
    entity: Literal["player", "team"] = "player"
    dataset: Literal["batting_performances", "bowling_performances", "team_results"]
    filters: list[Filter] = Field(default_factory=list, max_length=20)
    metrics: list[str] = Field(min_length=1, max_length=20)
    groupBy: list[GroupField] = Field(default=["player_id"], min_length=1, max_length=3)
    orderBy: list[OrderBy] = Field(default_factory=list, max_length=3)
    limit: int = Field(default=10, ge=1, le=100)

    @model_validator(mode="before")
    @classmethod
    def _derive_entity(cls, data):
        if isinstance(data, dict) and data.get("dataset") == "team_results":
            data = {**data, "entity": "team"}
            data.setdefault("groupBy", ["team"])
        return data

    @property
    def id_key(self) -> str:
        return "team" if self.dataset == "team_results" else "player_id"

    @property
    def label_key(self) -> str:
        return "team" if self.dataset == "team_results" else "player"

    @model_validator(mode="after")
    def _validate(self) -> "AnalyticsQuery":
        if (self.entity == "team") != (self.dataset == "team_results"):
            raise ValueError("entity and dataset do not match")
        allowed = METRICS[self.dataset]
        if bad := [m for m in self.metrics if m not in allowed]:
            raise ValueError(f"unknown metrics for {self.dataset}: {bad}")
        if self.id_key not in self.groupBy:
            raise ValueError(f"groupBy must include {self.id_key}")
        for f in self.filters:
            if self.entity == "team" and f.field in PLAYER_ONLY_FIELDS:
                raise ValueError(f"filter {f.field} is not available for team queries")
            if f.field in TEXT_FIELDS:
                if f.operator not in EQ_OPS:
                    raise ValueError(f"operator {f.operator} not allowed for {f.field}")
            elif f.field == "match_date":
                if f.operator not in CMP_OPS or not isinstance(f.value, str):
                    raise ValueError("match_date requires a comparison operator and ISO date string")
                date.fromisoformat(f.value)
            elif f.field in allowed:
                if f.operator == "in" or isinstance(f.value, (list, str)):
                    raise ValueError(f"metric filter {f.field} requires a numeric comparison")
            else:
                raise ValueError(f"unknown filter field: {f.field}")
            if f.field == "home_away" and not {*(f.value if isinstance(f.value, list) else [f.value])} <= {"home", "away"}:
                raise ValueError("home_away must be 'home' or 'away'")
            if f.operator == "in" and not isinstance(f.value, list):
                raise ValueError("operator 'in' requires a list value")
        valid_order = {*allowed, *self.groupBy}
        if bad := [o.field for o in self.orderBy if o.field not in valid_order]:
            raise ValueError(f"cannot order by: {bad}")
        return self
