from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.analytics.query_dsl import AnalyticsQuery
from app.analytics.cache import execute_query_cached
from app.analytics.query_executor import QueryResult
from app.database.session import get_session

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.post("/query", response_model=QueryResult)
def run_query(query: AnalyticsQuery, session: Session = Depends(get_session)) -> QueryResult:
    return execute_query_cached(session, query)
