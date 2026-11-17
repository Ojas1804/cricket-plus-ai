from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.widgets.schemas import WidgetSpec
from app.widgets.service import widget_service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

MAX_WIDGETS = 100


class AttachRequest(BaseModel):
    widgets: list[WidgetSpec] = Field(max_length=MAX_WIDGETS)


class LayoutItem(BaseModel):
    x: int = Field(ge=0, le=100)
    y: int = Field(ge=0, le=100000)
    w: int = Field(ge=1, le=100)
    h: int = Field(ge=1, le=1000)


class LayoutRequest(BaseModel):
    layout: dict[str, LayoutItem] = Field(max_length=MAX_WIDGETS)


@router.get("")
def get_dashboard() -> dict[str, Any]:
    return {"widgets": [w.model_dump(mode="json") for w in widget_service.all()], "layout": widget_service.layouts}


@router.post("/widgets", status_code=201)
def attach_widgets(body: AttachRequest) -> dict[str, int]:
    for w in body.widgets:
        widget_service.save(w)
    return {"attached": len(body.widgets)}


@router.delete("/widgets/{widget_id}", status_code=204)
def detach_widget(widget_id: str) -> None:
    widget_service.delete(widget_id)


@router.patch("/layout")
def update_layout(body: LayoutRequest) -> dict[str, int]:
    widget_service.layouts.update({k: v.model_dump() for k, v in body.layout.items() if k in {w.id for w in widget_service.all()}})
    return {"updated": len(body.layout)}
