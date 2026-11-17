from fastapi import APIRouter, Depends

from app.core.exceptions import CricketCanvasError
from app.live.models import InningsScore, LiveListResponse, MatchEnvelope
from app.live.service import LiveService, get_live_service
from app.live.widgets import build_live_widget
from app.widgets.schemas import WidgetSpec

router = APIRouter(prefix="/matches", tags=["matches"])


class LiveUnavailable(CricketCanvasError):
    status_code = 503


def live_service() -> LiveService:
    try:
        return get_live_service()
    except ValueError as e:
        raise LiveUnavailable(str(e)) from e


@router.get("/live", response_model=LiveListResponse)
def live_matches(service: LiveService = Depends(live_service)) -> LiveListResponse:
    return service.list_matches()


@router.get("/{match_id}", response_model=MatchEnvelope)
def match_details(match_id: str, service: LiveService = Depends(live_service)) -> MatchEnvelope:
    return service.get_match(match_id)


@router.get("/{match_id}/scorecard")
def match_scorecard(match_id: str, service: LiveService = Depends(live_service)) -> dict:
    env = service.get_match(match_id)
    innings: list[InningsScore] = env.match.innings
    return {"match_id": match_id, "innings": [i.model_dump(mode="json") for i in innings], "freshness": env.freshness.model_dump(mode="json")}


@router.get("/{match_id}/widget", response_model=WidgetSpec)
def match_widget(match_id: str, widgetId: str | None = None, service: LiveService = Depends(live_service)) -> WidgetSpec:
    """Stateless scorecard widget for a live match; used by the browser to poll without depending on stored widgets."""
    return build_live_widget(service.get_match(match_id), service.refresh_seconds, widgetId)
