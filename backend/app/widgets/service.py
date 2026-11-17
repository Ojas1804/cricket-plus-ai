from datetime import datetime, timezone

from app.core.exceptions import NotFoundError
from app.widgets.schemas import WidgetSpec


class WidgetService:
    def __init__(self) -> None:
        self._widgets: dict[str, WidgetSpec] = {}
        self.layouts: dict[str, dict[str, int]] = {}

    def save(self, widget: WidgetSpec) -> WidgetSpec:
        self._widgets[widget.id] = widget
        return widget

    def get(self, widget_id: str) -> WidgetSpec:
        if widget_id not in self._widgets:
            raise NotFoundError(f"Widget {widget_id} not found")
        return self._widgets[widget_id]

    def refresh(self, widget_id: str) -> WidgetSpec:
        widget = self.get(widget_id)
        meta = widget.metadata.model_copy(update={"lastUpdated": datetime.now(timezone.utc)})
        return self.save(widget.model_copy(update={"metadata": meta}))

    def delete(self, widget_id: str) -> None:
        self.get(widget_id)
        del self._widgets[widget_id]
        self.layouts.pop(widget_id, None)

    def all(self) -> list[WidgetSpec]:
        return list(self._widgets.values())


widget_service = WidgetService()
