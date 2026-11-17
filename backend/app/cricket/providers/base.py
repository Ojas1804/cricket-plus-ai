from typing import Any, Protocol

from app.live.models import LiveMatch, MatchSummary


class ProviderError(Exception):
    pass


class HistoricalDataProvider(Protocol):
    def fetch_dataset(self, name: str) -> Any: ...


class LiveScoreProvider(Protocol):
    name: str
    is_mock: bool

    def list_live_matches(self) -> list[MatchSummary]: ...

    def get_scorecard(self, match_id: str) -> LiveMatch: ...


class FixtureProvider(Protocol):
    def list_fixtures(self, days_ahead: int) -> list[Any]: ...


class PlayerImageProvider(Protocol):
    def image_url(self, player_name: str) -> str | None: ...
