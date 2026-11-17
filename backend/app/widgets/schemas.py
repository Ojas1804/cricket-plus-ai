from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class WidgetType(str, Enum):
    SCORECARD = "scorecard"
    LEADERBOARD = "leaderboard"
    TABLE = "table"
    CHART = "chart"
    PLAYER_PROFILE = "player_profile"
    COMPARISON = "comparison"
    TEXT = "text"
    IMAGE = "image"
    TIMELINE = "timeline"
    FIXTURE = "fixture"
    POINTS_TABLE = "points_table"
    ADVANCED_STATS = "advanced_stats"


class WidgetData(BaseModel):
    columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)


class WidgetMetadata(BaseModel):
    source: str
    lastUpdated: datetime
    filters: dict[str, Any] = Field(default_factory=dict)
    coverage: dict[str, Any] = Field(default_factory=dict)
    isMock: bool = False
    provenance: dict[str, Any] = Field(default_factory=dict)


class WidgetInteractions(BaseModel):
    selectableRows: bool = False
    linkedEntity: str | None = None
    subscribesTo: list[str] = Field(default_factory=list)


class WidgetSpec(BaseModel):
    schemaVersion: Literal["1.0"] = "1.0"
    id: str
    type: WidgetType
    title: str
    description: str = ""
    query: dict[str, Any] = Field(default_factory=dict)
    data: WidgetData
    metadata: WidgetMetadata
    interactions: WidgetInteractions = Field(default_factory=WidgetInteractions)


class FocusRequest(BaseModel):
    entityType: Literal["PLAYER"]
    entityId: int


class PromptAction(str, Enum):
    ADD = "ADD"
    UPDATE = "UPDATE"


class PromptRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=1000)
    action: PromptAction = PromptAction.ADD
    targetWidgetId: str | None = None


class PromptResponse(BaseModel):
    executionId: str
    status: Literal["COMPLETED", "PENDING", "FAILED", "CLARIFICATION_REQUIRED"]
    widgets: list[WidgetSpec]
    message: str | None = None
    options: list[str] = Field(default_factory=list)
