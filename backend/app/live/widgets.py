from app.ai.visualization_planner import new_widget_id, text_widget
from app.live.models import MatchEnvelope
from app.live.service import LiveService
from app.widgets.schemas import WidgetData, WidgetMetadata, WidgetSpec, WidgetType

MAX_LIVE_WIDGETS = 6


def stale_warning(env: MatchEnvelope) -> list[str]:
    f = env.freshness
    if not f.stale:
        return []
    when = f"{f.last_success_at:%Y-%m-%d %H:%M:%S} UTC" if f.last_success_at else "never"
    return [f"Live data is stale and is not being shown as live. Last successful update: {when}." + (f" {f.error}." if f.error else "")]


def build_live_widget(env: MatchEnvelope, refresh_seconds: int, widget_id: str | None = None) -> WidgetSpec:
    m, f = env.match, env.freshness
    return WidgetSpec(
        id=widget_id or new_widget_id(), type=WidgetType.SCORECARD, title=m.title, description=m.status_text,
        query={"live": {"matchId": m.match_id, "refreshSeconds": refresh_seconds}},
        data=WidgetData(extra={**m.model_dump(mode="json"), "stale": f.stale}),
        metadata=WidgetMetadata(
            source=f"live:{f.provider}", lastUpdated=f.last_success_at or m.updated_at, isMock=f.is_mock,
            provenance={"stale": f.stale, "warnings": stale_warning(env), "provider": f.provider, "error": f.error,
                        "lastSuccessAt": f.last_success_at.isoformat() if f.last_success_at else None}))


def live_widgets(service: LiveService) -> list[WidgetSpec]:
    res = service.list_matches()
    if res.matches:
        return [build_live_widget(e, service.refresh_seconds) for e in res.matches[:MAX_LIVE_WIDGETS]]
    warnings = stale_warning(MatchEnvelope.model_construct(match=None, freshness=res.freshness)) if res.freshness.error else []
    text = ("The live score provider is unavailable, so live matches cannot be shown right now." if res.freshness.error
            else "There are no live matches at the moment.")
    return [text_widget("Live matches", text, f"live:{res.freshness.provider}", warnings, mock=res.freshness.is_mock)]
