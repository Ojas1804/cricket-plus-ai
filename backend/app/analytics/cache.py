"""Result cache for analytics queries. Keys include the latest ingestion marker, so new data invalidates entries automatically."""
import hashlib
from functools import lru_cache

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analytics.query_dsl import AnalyticsQuery
from app.analytics.query_executor import QueryResult, execute_query
from app.core.config import get_settings
from app.cricket.models import DataIngestionLog
from app.live.cache import LiveCache, build_cache


@lru_cache
def _cache() -> LiveCache:
    return build_cache(get_settings().redis_url)[0]


def reset_cache() -> None:
    _cache.cache_clear()


def _key(session: Session, query: AnalyticsQuery) -> str:
    marker = session.execute(select(func.max(DataIngestionLog.id), func.max(DataIngestionLog.ingested_at))).one()
    digest = hashlib.sha256(f"{query.model_dump_json()}|{marker[0]}|{marker[1]}".encode()).hexdigest()
    return f"analytics:{digest}"


def execute_query_cached(session: Session, query: AnalyticsQuery, use_cache: bool = True) -> QueryResult:
    """Cached results are marked in provenance; executedAt keeps the original execution time."""
    ttl = get_settings().analytics_cache_ttl_seconds
    if ttl <= 0:
        return execute_query(session, query)
    key = _key(session, query)
    if use_cache and (hit := _cache().get(key)):
        result = QueryResult.model_validate(hit)
        result.provenance["cached"] = True
        return result
    result = execute_query(session, query)
    result.provenance["cached"] = False
    _cache().set(key, result.model_dump(mode="json"), ttl)
    return result
