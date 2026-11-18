"""Ordered failover across live-score providers.

Discovery uses the first provider that succeeds with at least one live match. Each match id is routed back to the
provider that owns it (remembered from discovery, otherwise chosen by id format). Ids are not translated between
providers, so a scorecard failure is not retried elsewhere; the service keeps the last known score instead.
"""
import logging

from app.cricket.providers.base import LiveScoreProvider, ProviderError
from app.live.models import LiveMatch, MatchSummary

logger = logging.getLogger(__name__)


class FailoverProvider:
    name = "auto"

    def __init__(self, providers: list[LiveScoreProvider]) -> None:
        if not providers:
            raise ValueError("FailoverProvider needs at least one provider")
        self.providers = providers
        self._owners: dict[str, LiveScoreProvider] = {}

    @property
    def is_mock(self) -> bool:
        return all(p.is_mock for p in self.providers)

    def list_live_matches(self) -> list[MatchSummary]:
        last_error: Exception | None = None
        succeeded = False
        for provider in self.providers:
            try:
                matches = provider.list_live_matches()
            except Exception as e:
                last_error = e
                logger.warning("Live discovery failed on %s: %s", provider.name, type(e).__name__)
                continue
            succeeded = True
            if matches:
                self._owners.update({m.match_id: provider for m in matches})
                return matches
        if not succeeded:
            raise ProviderError("All live score providers failed") from last_error
        return []

    def get_scorecard(self, match_id: str) -> LiveMatch:
        owner = self._owners.get(match_id)
        candidates = [owner] if owner else [p for p in self.providers if getattr(p, "accepts_id", lambda _: True)(match_id)]
        last_error: Exception | None = None
        for provider in candidates:
            try:
                return provider.get_scorecard(match_id)
            except Exception as e:
                last_error = e
        raise ProviderError("No live score provider could fetch this match") from last_error
