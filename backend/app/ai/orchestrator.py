import json
import logging
import re
import uuid
from functools import lru_cache

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.entity_resolver import AmbiguousEntity, EntityResolutionError, resolve_competition, resolve_player, resolve_team, resolve_venue
from app.ai.intent import generate_explanation, interpret_prompt
from app.ai.mock_orchestrator import handle_mock_prompt
from app.ai.providers import LLMError, LLMProvider, get_provider
from app.ai.query_planner import plan_query
from app.ai.visualization_planner import Presentation, build_widget, new_widget_id, text_widget
from app.analytics.query_dsl import AnalyticsQuery
from app.analytics.cache import execute_query_cached
from app.analytics.query_executor import execute_query
from app.core.exceptions import CricketCanvasError, NotFoundError, ValidationFailure
from app.cricket.models import Match, Player
from app.widgets.schemas import PromptAction, PromptRequest, PromptResponse, WidgetSpec
from app.live.service import get_live_service
from app.live.widgets import build_live_widget, live_widgets
from app.widgets.profile import build_profile_widget
from app.widgets.service import widget_service

logger = logging.getLogger(__name__)

NO_DATA_MESSAGE = ("No historical cricket data has been ingested yet. Download Cricsheet JSON into data/raw/ and run "
                   "`python -m app.cricket.ingestion.cricsheet <path>` from the backend folder.")


class LLMUnavailable(CricketCanvasError):
    status_code = 502


@lru_cache
def _provider() -> LLMProvider | None:
    return get_provider()


def _execution_id() -> str:
    return f"execution-{uuid.uuid4().hex[:8]}"


def _clarify(message: str, options: list[str] | None = None) -> PromptResponse:
    return PromptResponse(executionId=_execution_id(), status="CLARIFICATION_REQUIRED", widgets=[], message=message, options=options or [])


def _resolve_mentions(session: Session, entities) -> dict[str, list[dict]]:
    resolved: dict[str, list[dict]] = {"players": [], "teams": [], "competitions": [], "venues": []}
    for key, fn in (("players", resolve_player), ("teams", resolve_team), ("competitions", resolve_competition), ("venues", resolve_venue)):
        for mention in getattr(entities, key):
            r = fn(session, mention)
            item = {"mention": mention, "name": r.label}
            if key == "players":
                item["player_id"] = r.value
            resolved[key].append(item)
    return resolved


def _clarification_for(e: EntityResolutionError) -> PromptResponse:
    if isinstance(e, AmbiguousEntity):
        return _clarify(f"'{e.mention}' matches several {e.entity_type}s: {', '.join(e.options)}. "
                        "Please repeat your request using one of these exact names.", e.options)
    return _clarify(f"I couldn't find a {e.entity_type} matching '{e.mention}' in the ingested data. "
                    "The dataset may not cover it, or the name may be spelled differently.")


LIVE_REQUEST = re.compile(r"\b(live|in progress|ongoing|currently (running|playing))\b.*\b(match|matches|score|scores|scorecard|cricket)\b"
                          r"|\b(match|matches|score|scores|scorecard)\b.*\b(live|in progress|ongoing)\b", re.IGNORECASE)


def _live_response() -> PromptResponse:
    widgets = live_widgets(get_live_service())
    for w in widgets:
        widget_service.save(w)
    return PromptResponse(executionId=_execution_id(), status="COMPLETED", widgets=widgets)


def handle_prompt(req: PromptRequest, session: Session, provider: LLMProvider | None = None) -> PromptResponse:
    if req.action == PromptAction.ADD and LIVE_REQUEST.search(req.prompt):
        return _live_response()
    provider = provider or _provider()
    if provider is None:
        return handle_mock_prompt(req)
    try:
        return _run_pipeline(req, session, provider)
    except EntityResolutionError as e:
        return _clarification_for(e)
    except LLMError as e:
        raise LLMUnavailable(str(e)) from e
    except (ValueError, KeyError) as e:
        logger.warning("Plan rejected after retry: %s", type(e).__name__)
        return _clarify("I couldn't turn that into a valid analysis. Try rephrasing, for example: "
                        "\"Top 10 run scorers in the IPL since 2020\".")


def _run_pipeline(req: PromptRequest, session: Session, provider: LLMProvider) -> PromptResponse:
    existing: WidgetSpec | None = None
    if req.action == PromptAction.UPDATE:
        if not req.targetWidgetId:
            raise NotFoundError("targetWidgetId is required for UPDATE")
        existing = widget_service.get(req.targetWidgetId)
    existing_query = existing.query if existing and "dsl" in existing.query else None
    existing_json = json.dumps(existing_query) if existing_query else None

    intent = interpret_prompt(provider, req.prompt, existing_json)
    if intent.clarification_question or intent.kind == "unsupported":
        return _clarify(intent.clarification_question or "I can only help with cricket questions and statistics.")

    widget_id = existing.id if existing else None
    if intent.kind == "explain":
        text = generate_explanation(provider, req.prompt)
        widgets = [text_widget("Explanation", text, "llm_explanation",
                               ["AI-generated explanation of a concept; not computed from the dataset."], widget_id)]
    elif intent.kind == "live":
        widgets = live_widgets(get_live_service())
        if widget_id:
            widgets = [widgets[0].model_copy(update={"id": widget_id})]
    else:
        widgets = _run_analytics(req, session, provider, intent, existing_query, widget_id)
        if isinstance(widgets, PromptResponse):
            return widgets

    for w in widgets:
        widget_service.save(w)
    return PromptResponse(executionId=_execution_id(), status="COMPLETED", widgets=widgets)


def _run_analytics(req, session, provider, intent, existing_query, widget_id) -> list[WidgetSpec] | PromptResponse:
    if not session.scalar(select(func.count()).select_from(Match)):
        return [text_widget("No data available", NO_DATA_MESSAGE, "internal_analytics", [NO_DATA_MESSAGE], widget_id)]
    resolved = _resolve_mentions(session, intent.entities)
    plan, planned = plan_query(provider, session, req.prompt, intent, resolved, existing_query)
    if not planned:
        return _clarify(plan.unanswerable_reason or "That can't be answered from the available cricket datasets.")
    if widget_id:
        planned = planned[:1]
    widgets = []
    for i, (pq, dsl, notes) in enumerate(planned):
        res = execute_query_cached(session, dsl)
        pres = Presentation(pq.title, pq.description, pq.visualization, pq.chart_type)
        widgets.append(build_widget(pres, dsl, res, widget_id if i == 0 else None, notes))
    return widgets


def refresh_widget(session: Session, widget_id: str) -> WidgetSpec:
    widget = widget_service.get(widget_id)
    if "live" in widget.query:
        service = get_live_service()
        return widget_service.save(build_live_widget(service.get_match(widget.query["live"]["matchId"]), service.refresh_seconds, widget.id))
    if "profile" in widget.query:
        return widget_service.save(build_profile_widget(session, widget.query["profile"]["playerId"], widget.id))
    if "dsl" not in widget.query:
        return widget_service.refresh(widget_id)
    dsl = AnalyticsQuery(**widget.query["dsl"])
    pres = Presentation(**widget.query["presentation"])
    notes = widget.metadata.provenance.get("notes", [])
    return widget_service.save(build_widget(pres, dsl, execute_query(session, dsl), widget.id, notes))


FOCUSABLE = {"player_profile", "chart", "table"}


def focus_widget(session: Session, widget_id: str, player_id: int) -> WidgetSpec:
    """Re-scope a widget to a selected player (cross-widget interaction). Only the player filter changes."""
    widget = widget_service.get(widget_id)
    if widget.type.value not in FOCUSABLE:
        raise ValidationFailure(f"A {widget.type.value} widget cannot follow a single selected player")
    if "profile" in widget.query:
        return widget_service.save(build_profile_widget(session, player_id, widget.id))
    if "dsl" not in widget.query:
        raise ValidationFailure("This widget was not created from the analytics engine and cannot be linked")

    new = session.get(Player, player_id)
    if not new:
        raise NotFoundError(f"Player {player_id} not found")
    dsl = AnalyticsQuery(**widget.query["dsl"])
    if dsl.entity != "player":
        raise ValidationFailure("Team widgets cannot follow a selected player")
    old_ids = [f.value for f in dsl.filters if f.field == "player_id" and not isinstance(f.value, list)]
    old = session.get(Player, int(old_ids[0])) if old_ids else None
    spec = dsl.model_dump()
    spec["filters"] = [f for f in spec["filters"] if f["field"] not in ("player", "player_id")]
    spec["filters"].append({"field": "player_id", "operator": "equals", "value": player_id})
    dsl = AnalyticsQuery(**spec)

    pres = Presentation(**widget.query["presentation"])
    pres.title = (pres.title.replace(old.display_name, new.display_name) if old and old.display_name in pres.title
                  else f"{pres.title} - {new.display_name}")
    notes = widget.metadata.provenance.get("notes", [])
    return widget_service.save(build_widget(pres, dsl, execute_query(session, dsl), widget.id, notes))
