from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.ai.orchestrator import focus_widget as focus
from app.ai.orchestrator import refresh_widget as refresh
from app.database.session import get_session

from app.widgets.schemas import FocusRequest, WidgetData, WidgetSpec
from app.widgets.service import widget_service

router = APIRouter(prefix="/widgets", tags=["widgets"])


@router.post("", response_model=WidgetSpec, status_code=201)
def create_widget(widget: WidgetSpec) -> WidgetSpec:
    return widget_service.save(widget)


@router.post("/{widget_id}/refresh", response_model=WidgetSpec)
def refresh_widget(widget_id: str, session: Session = Depends(get_session)) -> WidgetSpec:
    return refresh(session, widget_id)


@router.post("/{widget_id}/focus", response_model=WidgetSpec)
def focus_widget(widget_id: str, body: FocusRequest, session: Session = Depends(get_session)) -> WidgetSpec:
    return focus(session, widget_id, body.entityId)


@router.get("/{widget_id}", response_model=WidgetSpec)
def get_widget(widget_id: str) -> WidgetSpec:
    return widget_service.get(widget_id)


@router.get("/{widget_id}/data", response_model=WidgetData)
def get_widget_data(widget_id: str) -> WidgetData:
    return widget_service.get(widget_id).data


@router.delete("/{widget_id}", status_code=204)
def delete_widget(widget_id: str) -> None:
    widget_service.delete(widget_id)
