import uuid
from datetime import datetime, timezone

from app.core.exceptions import NotFoundError
from app.widgets.schemas import (
    PromptAction, PromptRequest, PromptResponse, WidgetData, WidgetInteractions,
    WidgetMetadata, WidgetSpec, WidgetType,
)
from app.live.service import get_live_service
from app.live.widgets import live_widgets
from app.widgets.service import widget_service


def _meta(filters: dict | None = None) -> WidgetMetadata:
    return WidgetMetadata(source="mock", lastUpdated=datetime.now(timezone.utc), filters=filters or {}, isMock=True)


def _new_id() -> str:
    return f"widget-{uuid.uuid4().hex[:8]}"


def _leaderboard(widget_id: str, min_matches: int | None = None) -> WidgetSpec:
    players = [("Virat Kohli", 8004, 252), ("Shikhar Dhawan", 6769, 222), ("David Warner", 6567, 184),
               ("Rohit Sharma", 6211, 257), ("Suresh Raina", 5528, 205), ("MS Dhoni", 5243, 264)]
    rows = [{"rank": i + 1, "player": n, "runs": r, "matches": m} for i, (n, r, m) in enumerate(players)
            if not min_matches or m >= min_matches]
    return WidgetSpec(
        id=widget_id, type=WidgetType.LEADERBOARD, title="Top IPL Run Scorers",
        description="Highest career run totals in IPL (mock data)",
        query={"competition": "IPL", "metric": "runs", "limit": 10, "minMatches": min_matches},
        data=WidgetData(columns=["rank", "player", "runs", "matches"], rows=rows),
        metadata=_meta({"minMatches": min_matches} if min_matches else {}),
        interactions=WidgetInteractions(selectableRows=True, linkedEntity="player"),
    )


def _comparison(widget_id: str) -> WidgetSpec:
    return WidgetSpec(
        id=widget_id, type=WidgetType.COMPARISON, title="Virat Kohli vs Rohit Sharma",
        description="Career comparison (mock data)",
        query={"players": ["Virat Kohli", "Rohit Sharma"]},
        data=WidgetData(columns=["metric", "Virat Kohli", "Rohit Sharma"], rows=[
            {"metric": "Runs", "Virat Kohli": 8004, "Rohit Sharma": 6211},
            {"metric": "Average", "Virat Kohli": 38.7, "Rohit Sharma": 29.6},
            {"metric": "Strike rate", "Virat Kohli": 131.9, "Rohit Sharma": 130.4},
        ]), metadata=_meta())


def _chart(widget_id: str) -> WidgetSpec:
    return WidgetSpec(
        id=widget_id, type=WidgetType.CHART, title="Runs by Year",
        description="Mock performance trend",
        query={"metric": "runs", "groupBy": "year"},
        data=WidgetData(columns=["year", "runs"],
                        rows=[{"year": y, "runs": r} for y, r in
                              [(2019, 464), (2020, 466), (2021, 405), (2022, 341), (2023, 639)]],
                        extra={"chartType": "line", "x": "year", "y": "runs"}),
        metadata=_meta())


def _profile(widget_id: str) -> WidgetSpec:
    return WidgetSpec(
        id=widget_id, type=WidgetType.PLAYER_PROFILE, title="Virat Kohli",
        description="Career profile (mock data)",
        data=WidgetData(extra={"name": "Virat Kohli", "stats": {
            "Role": "Batter", "Country": "India", "IPL runs": 8004, "IPL average": 38.7, "IPL strike rate": 131.9}}),
        metadata=_meta())


def _text(widget_id: str, prompt: str) -> WidgetSpec:
    return WidgetSpec(
        id=widget_id, type=WidgetType.TEXT, title="Analysis",
        data=WidgetData(extra={"text": f'Mock response for: "{prompt}". '
                                       "Real analysis arrives with the AI query engine (Milestone 3)."}),
        metadata=_meta())


def handle_mock_prompt(req: PromptRequest) -> PromptResponse:
    text = req.prompt.lower()
    execution_id = f"execution-{uuid.uuid4().hex[:8]}"

    if req.action == PromptAction.UPDATE:
        if not req.targetWidgetId:
            raise NotFoundError("targetWidgetId is required for UPDATE")
        existing = widget_service.get(req.targetWidgetId)
        min_matches = 50 if "50" in text else None
        updated = (_leaderboard(existing.id, min_matches) if existing.type == WidgetType.LEADERBOARD
                   else existing.model_copy(update={"metadata": _meta(existing.metadata.filters)}))
        widget_service.save(updated)
        return PromptResponse(executionId=execution_id, status="COMPLETED", widgets=[updated])

    if "compare" in text:
        widgets = [_comparison(_new_id()), _chart(_new_id())] if "trend" in text else [_comparison(_new_id())]
    elif "live" in text or "score" in text and "scorer" not in text:
        widgets = live_widgets(get_live_service())
    elif any(k in text for k in ("profile", "career")):
        widgets = [_profile(_new_id())]
    elif any(k in text for k in ("top", "scorer", "leaderboard")):
        widgets = [_leaderboard(_new_id())]
    elif any(k in text for k in ("chart", "trend", "evolution", "by year")):
        widgets = [_chart(_new_id())]
    else:
        widgets = [_text(_new_id(), req.prompt)]
    for w in widgets:
        widget_service.save(w)
    return PromptResponse(executionId=execution_id, status="COMPLETED", widgets=widgets)
