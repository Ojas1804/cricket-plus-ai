from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

DEFAULT_URL = "sqlite:///./data/cricket.db"


@lru_cache
def get_engine() -> Engine:
    return create_engine(get_settings().database_url or DEFAULT_URL, pool_pre_ping=True)


def get_session() -> Iterator[Session]:
    with sessionmaker(bind=get_engine(), expire_on_commit=False)() as session:
        yield session
