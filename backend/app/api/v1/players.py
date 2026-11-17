from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.analytics.query_dsl import AnalyticsQuery, Filter
from app.analytics.cache import execute_query_cached
from app.core.exceptions import NotFoundError
from app.cricket.models import Player
from app.database.session import get_session
from app.widgets.profile import build_profile_widget
from app.widgets.schemas import WidgetSpec
from app.widgets.service import widget_service

router = APIRouter(prefix="/players", tags=["players"])

BATTING = ["matches", "innings", "runs", "balls_faced", "fours", "sixes", "dismissals", "fifties", "hundreds", "batting_average", "strike_rate"]
BOWLING = ["matches", "innings", "balls_bowled", "runs_conceded", "wickets", "maidens", "economy", "bowling_average", "bowling_strike_rate"]


def _player(session: Session, player_id: int) -> Player:
    player = session.get(Player, player_id)
    if not player:
        raise NotFoundError(f"Player {player_id} not found")
    return player


@router.get("/{player_id}")
def get_player(player_id: int, session: Session = Depends(get_session)) -> dict[str, Any]:
    p = _player(session, player_id)
    return {"id": p.id, "full_name": p.full_name, "display_name": p.display_name, "country": p.country,
            "role": p.role, "batting_style": p.batting_style, "bowling_style": p.bowling_style, "aliases": p.aliases}


@router.get("/{player_id}/statistics")
def get_player_statistics(player_id: int, format: str | None = None, session: Session = Depends(get_session)) -> dict[str, Any]:
    _player(session, player_id)
    filters = [Filter(field="player_id", operator="equals", value=player_id)]
    if format:
        filters.append(Filter(field="format", operator="equals", value=format))
    out: dict[str, Any] = {}
    for key, dataset, metrics in (("batting", "batting_performances", BATTING), ("bowling", "bowling_performances", BOWLING)):
        res = execute_query_cached(session, AnalyticsQuery(dataset=dataset, metrics=metrics, filters=filters,
                                                    groupBy=["player_id", "format"], limit=100))
        out[key] = {"columns": res.columns, "rows": res.rows, "provenance": res.provenance}
    return out


@router.post("/{player_id}/profile-widget", response_model=WidgetSpec, status_code=201)
def create_profile_widget(player_id: int, session: Session = Depends(get_session)) -> WidgetSpec:
    return widget_service.save(build_profile_widget(session, player_id))
