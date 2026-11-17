"""Normalized live-match models. Providers must map their raw responses to these; raw formats never reach the frontend."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class BatterLine(BaseModel):
    player: str
    runs: int
    balls: int
    fours: int = 0
    sixes: int = 0
    strike_rate: float | None = None
    on_strike: bool = False
    dismissal: str | None = None


class BowlerLine(BaseModel):
    player: str
    overs: str
    maidens: int = 0
    runs: int
    wickets: int
    economy: float | None = None


class OverSummary(BaseModel):
    over: int
    balls: list[str]
    runs: int


class Partnership(BaseModel):
    runs: int
    balls: int
    batters: list[str]


class InningsScore(BaseModel):
    number: int
    team: str
    runs: int
    wickets: int
    overs: str
    legal_balls: int
    completed: bool
    batting: list[BatterLine] = Field(default_factory=list)
    bowling: list[BowlerLine] = Field(default_factory=list)
    fall_of_wickets: list[str] = Field(default_factory=list)
    did_not_bat: list[str] = Field(default_factory=list)


class MatchSummary(BaseModel):
    match_id: str
    title: str
    format: str
    status: Literal["UPCOMING", "LIVE", "COMPLETED"]


class LiveMatch(BaseModel):
    match_id: str
    title: str
    format: str
    status: Literal["UPCOMING", "LIVE", "COMPLETED"]
    status_text: str
    teams: list[str]
    venue: str | None = None
    current_innings: int | None = None
    innings: list[InningsScore] = Field(default_factory=list)
    current_run_rate: float | None = None
    required_run_rate: float | None = None
    target: int | None = None
    runs_required: int | None = None
    balls_remaining: int | None = None
    partnership: Partnership | None = None
    recent_overs: list[OverSummary] = Field(default_factory=list)
    updated_at: datetime


class Freshness(BaseModel):
    last_success_at: datetime | None
    stale: bool
    error: str | None = None
    provider: str
    is_mock: bool


class MatchEnvelope(BaseModel):
    match: LiveMatch
    freshness: Freshness


class LiveListResponse(BaseModel):
    matches: list[MatchEnvelope]
    freshness: Freshness
