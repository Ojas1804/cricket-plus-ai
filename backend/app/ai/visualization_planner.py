import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from app.analytics.query_dsl import AnalyticsQuery
from app.analytics.query_executor import QueryResult
from app.widgets.schemas import WidgetData, WidgetInteractions, WidgetMetadata, WidgetSpec, WidgetType


@dataclass
class Presentation:
    title: str
    description: str
    visualization: str
    chart_type: str


def new_widget_id() -> str:
    return f"widget-{uuid.uuid4().hex[:8]}"


def _chart(dsl: AnalyticsQuery, res: QueryResult, chart_type: str) -> WidgetData:
    metric = dsl.metrics[0]
    lk = dsl.label_key
    split = next((g for g in dsl.groupBy if g != dsl.id_key), None)
    extra: dict[str, Any] = {"yLabel": metric, "chartType": chart_type}
    label = lambda r: r[lk] if not split else f"{r[lk]} - {r[split]}"  # noqa: E731
    if chart_type == "scatter" and len(dsl.metrics) >= 2:
        y = dsl.metrics[1]
        extra.update(xLabel=metric, yLabel=y, points=[{"name": label(r), "value": [r[metric], r[y]]}
                                                    for r in res.rows if r[metric] is not None and r[y] is not None])
        return WidgetData(columns=res.columns, rows=res.rows, extra=extra)
    if chart_type == "pie":
        extra["slices"] = [{"name": label(r), "value": r[metric]} for r in res.rows if r[metric] is not None and r[metric] > 0]
        return WidgetData(columns=res.columns, rows=res.rows, extra=extra)
    splits = [g for g in dsl.groupBy if g != dsl.id_key]
    if chart_type == "radar" and not splits and len(dsl.metrics) >= 3 and res.rows:
        maxima = {k: max((r[k] or 0) for r in res.rows) for k in dsl.metrics}
        extra["indicators"] = [{"name": k.replace("_", " "), "max": round(maxima[k] * 1.15, 2) or 1} for k in dsl.metrics]
        extra["radarSeries"] = [{"name": r[lk], "value": [r[k] or 0 for k in dsl.metrics]} for r in res.rows]
        return WidgetData(columns=res.columns, rows=res.rows, extra=extra)
    if chart_type == "heatmap" and splits and (len(splits) == 1 or len({r[lk] for r in res.rows}) == 1):
        xk, yk = splits[0], (splits[1] if len(splits) > 1 else lk)
        xs = sorted({str(r[xk]) for r in res.rows})
        ys = sorted({str(r[yk]) for r in res.rows}) if len(splits) > 1 else list(dict.fromkeys(str(r[yk]) for r in res.rows))
        cells = [[xs.index(str(r[xk])), ys.index(str(r[yk])), r[metric]] for r in res.rows if r[metric] is not None]
        values = [c[2] for c in cells]
        extra.update(xCategories=xs, yCategories=ys, cells=cells, min=min(values, default=0), max=max(values, default=1))
        return WidgetData(columns=res.columns, rows=res.rows, extra=extra)
    extra["chartType"] = "bar" if chart_type in ("scatter", "pie", "radar", "heatmap") else chart_type
    if split:
        categories = sorted({str(r[split]) for r in res.rows})
        by_player: dict[str, dict[str, Any]] = {}
        for r in res.rows:
            by_player.setdefault(r[lk], {})[str(r[split])] = r[metric]
        extra["series"] = [{"name": p, "data": [vals.get(c) for c in categories]} for p, vals in by_player.items()]
        extra["categories"] = categories
    else:
        extra["categories"] = [r[lk] for r in res.rows]
        extra["series"] = [{"name": metric, "data": [r[metric] for r in res.rows]}]
    return WidgetData(columns=res.columns, rows=res.rows, extra=extra)


def _comparison(dsl: AnalyticsQuery, res: QueryResult) -> WidgetData:
    lk = dsl.label_key
    players = [r[lk] for r in res.rows]
    rows = [{"metric": m.replace("_", " "), **{r[lk]: r[m] for r in res.rows}} for m in dsl.metrics]
    return WidgetData(columns=["metric", *players], rows=rows)


def build_widget(pres: Presentation, dsl: AnalyticsQuery, res: QueryResult, widget_id: str | None = None,
                 notes: list[str] | None = None) -> WidgetSpec:
    viz = pres.visualization
    if viz == "comparison" and dsl.groupBy != [dsl.id_key]:
        viz = "table"
    selectable = False
    if viz == "leaderboard":
        rows = [{"rank": i + 1, **r} for i, r in enumerate(res.rows)]
        data, wtype, selectable = WidgetData(columns=["rank", *res.columns], rows=rows), WidgetType.LEADERBOARD, dsl.entity == "player"
    elif viz == "comparison":
        data, wtype = _comparison(dsl, res), WidgetType.COMPARISON
    elif viz == "chart":
        data, wtype = _chart(dsl, res, pres.chart_type), WidgetType.CHART
    elif viz == "profile" and res.rows and dsl.entity == "player":
        row = res.rows[0]
        stats = {k.replace("_", " "): v for k, v in row.items() if k in dsl.metrics}
        data, wtype = WidgetData(columns=res.columns, rows=res.rows, extra={"name": row["player"], "stats": stats}), WidgetType.PLAYER_PROFILE
    else:
        data, wtype = WidgetData(columns=res.columns, rows=res.rows), WidgetType.TABLE
        selectable = "player" in res.columns

    prov = {**res.provenance, "notes": [*res.provenance.get("notes", []), *(notes or [])]}
    return WidgetSpec(
        id=widget_id or new_widget_id(), type=wtype, title=pres.title, description=pres.description,
        query={"dsl": dsl.model_dump(), "presentation": asdict(pres)}, data=data,
        metadata=WidgetMetadata(
            source="internal_analytics", lastUpdated=datetime.fromisoformat(res.provenance["executedAt"]),
            filters={f.field: f.value for f in dsl.filters}, coverage=res.provenance["coverage"], provenance=prov),
        interactions=WidgetInteractions(selectableRows=selectable, linkedEntity="player" if selectable else None))


def text_widget(title: str, text: str, source: str, warnings: list[str], widget_id: str | None = None, mock: bool = False) -> WidgetSpec:
    return WidgetSpec(
        id=widget_id or new_widget_id(), type=WidgetType.TEXT, title=title, data=WidgetData(extra={"text": text}),
        metadata=WidgetMetadata(source=source, lastUpdated=datetime.now().astimezone(), isMock=mock,
                                provenance={"warnings": warnings}))
