from datetime import datetime

from sqlalchemy.orm import Session

from app.analytics.query_dsl import AnalyticsQuery
from app.analytics.query_executor import execute_query
from app.core.exceptions import NotFoundError
from app.cricket.models import Player
from app.ai.visualization_planner import new_widget_id
from app.widgets.schemas import WidgetData, WidgetInteractions, WidgetMetadata, WidgetSpec, WidgetType

BATTING = ["matches", "innings", "runs", "batting_average", "strike_rate", "fifties", "hundreds"]
BOWLING = ["wickets", "bowling_average", "economy"]


def build_profile_widget(session: Session, player_id: int, widget_id: str | None = None) -> WidgetSpec:
    player = session.get(Player, player_id)
    if not player:
        raise NotFoundError(f"Player {player_id} not found")
    flt = [{"field": "player_id", "operator": "equals", "value": player_id}]
    bat = execute_query(session, AnalyticsQuery(dataset="batting_performances", metrics=BATTING, filters=flt))
    bowl = execute_query(session, AnalyticsQuery(dataset="bowling_performances", metrics=[*BOWLING, "balls_bowled"], filters=flt))

    stats: dict = {}
    if bat.rows:
        stats.update({k.replace("_", " "): bat.rows[0][k] for k in BATTING})
    if bowl.rows and bowl.rows[0]["balls_bowled"]:
        stats.update({k.replace("_", " "): bowl.rows[0][k] for k in BOWLING})

    prov = {**bat.provenance, "definitions": {**bat.provenance["definitions"], **bowl.provenance["definitions"]},
            "warnings": [] if stats else ["No performances for this player in the ingested data."]}
    return WidgetSpec(
        id=widget_id or new_widget_id(), type=WidgetType.PLAYER_PROFILE, title=player.display_name,
        description="Career summary across all ingested matches", query={"profile": {"playerId": player_id}},
        data=WidgetData(extra={"name": player.display_name, "stats": stats}),
        metadata=WidgetMetadata(source="internal_analytics", lastUpdated=datetime.fromisoformat(bat.provenance["executedAt"]),
                                coverage=bat.provenance["coverage"], provenance=prov),
        interactions=WidgetInteractions(subscribesTo=["PLAYER_SELECTED"]))
