import logging
import threading
import time
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from app.core.config import get_settings
from app.core.exceptions import NotFoundError
from app.cricket.providers.base import LiveScoreProvider, ProviderError
from app.live.cache import LiveCache, build_cache
from app.live.models import Freshness, LiveListResponse, LiveMatch, MatchEnvelope

logger = logging.getLogger(__name__)

INDEX_KEY = "live:index"
CACHE_TTL_SECONDS = 6 * 3600
STALE_FACTOR = 2
GENERIC_ERROR = "The live score provider is currently unavailable"


def _match_key(match_id: str) -> str:
    return f"live:match:{match_id}"


def _iso(dt: datetime) -> str:
    return dt.isoformat()


class LiveService:
    """Reads come from the cache. Only the poller (or one on-demand fetch when the cache is empty) calls the provider."""

    def __init__(self, provider: LiveScoreProvider, cache: LiveCache, refresh_seconds: int = 60,
                 clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc), min_call_interval: float = 0.0) -> None:
        self.provider, self.cache, self.refresh_seconds, self.clock = provider, cache, refresh_seconds, clock
        self.min_call_interval = min_call_interval
        self.poller_active = False
        self._refresh_lock = threading.Lock()
        self._call_lock = threading.Lock()
        self._last_call = 0.0

    def _call(self, fn, *args):
        with self._call_lock:
            wait = self.min_call_interval - (time.monotonic() - self._last_call)
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.monotonic()
        return fn(*args)

    @staticmethod
    def _error_text(e: Exception) -> str:
        return str(e) if isinstance(e, ProviderError) else GENERIC_ERROR

    def refresh_all(self) -> bool:
        with self._refresh_lock:
            return self._refresh_all()

    def _refresh_all(self) -> bool:
        now = self.clock()
        ok = True
        index = self.cache.get(INDEX_KEY) or {"ids": [], "tracked": [], "last_success_at": None, "error": None}
        try:
            summaries = self._call(self.provider.list_live_matches)
            index.update(ids=[s.match_id for s in summaries], last_success_at=_iso(now), error=None)
        except Exception as e:
            ok = False
            index["error"] = self._error_text(e)
            logger.warning("Live discovery failed: %s", type(e).__name__)

        tracked = list(dict.fromkeys([*index["ids"], *index.get("tracked", [])]))
        still_tracked = []
        for match_id in tracked:
            entry = self.cache.get(_match_key(match_id))
            try:
                match = self._call(self.provider.get_scorecard, match_id)
                entry = {"match": match.model_dump(mode="json"), "last_success_at": _iso(now), "error": None}
                if match.status != "COMPLETED":
                    still_tracked.append(match_id)
            except Exception as e:
                ok = False
                logger.warning("Live scorecard fetch failed for %s: %s", match_id, type(e).__name__)
                if entry is None:
                    continue
                entry["error"] = self._error_text(e)
                still_tracked.append(match_id)
            self.cache.set(_match_key(match_id), entry, CACHE_TTL_SECONDS)
        index["tracked"] = still_tracked
        self.cache.set(INDEX_KEY, index, CACHE_TTL_SECONDS)
        return ok

    def _freshness(self, last_success: str | None, error: str | None) -> Freshness:
        last = datetime.fromisoformat(last_success) if last_success else None
        limit = timedelta(seconds=STALE_FACTOR * self.refresh_seconds + 5)
        stale = bool(error) or last is None or self.clock() - last > limit
        return Freshness(last_success_at=last, stale=stale, error=error, provider=self.provider.name, is_mock=self.provider.is_mock)

    def _envelope(self, entry: dict) -> MatchEnvelope:
        return MatchEnvelope(match=LiveMatch.model_validate(entry["match"]), freshness=self._freshness(entry["last_success_at"], entry["error"]))

    def _ensure_index(self) -> dict:
        index = self.cache.get(INDEX_KEY)
        age_limit = timedelta(seconds=self.refresh_seconds)
        needs = index is None or (not self.poller_active and index["last_success_at"] is not None
                                  and self.clock() - datetime.fromisoformat(index["last_success_at"]) > age_limit)
        if needs:
            with self._refresh_lock:
                index = self.cache.get(INDEX_KEY)
                if index is None or needs:
                    self._refresh_all()
                index = self.cache.get(INDEX_KEY)
        return index or {"ids": [], "last_success_at": None, "error": GENERIC_ERROR}

    def list_matches(self) -> LiveListResponse:
        index = self._ensure_index()
        envelopes = []
        for match_id in index["ids"]:
            entry = self.cache.get(_match_key(match_id))
            if entry:
                envelopes.append(self._envelope(entry))
        return LiveListResponse(matches=envelopes, freshness=self._freshness(index["last_success_at"], index["error"]))

    def get_match(self, match_id: str) -> MatchEnvelope:
        entry = self.cache.get(_match_key(match_id))
        if entry is None:
            self._ensure_index()
            entry = self.cache.get(_match_key(match_id))
        if entry is None:
            raise NotFoundError(f"Live match {match_id} not found")
        return self._envelope(entry)


@lru_cache
def get_live_service() -> LiveService:
    s = get_settings()
    if s.live_score_provider != "mock":
        raise ValueError(f"Live score provider '{s.live_score_provider}' is not supported; configure LIVE_SCORE_PROVIDER=mock")
    from app.cricket.providers.mock_live import MockLiveProvider

    cache, shared = build_cache(s.redis_url)
    service = LiveService(MockLiveProvider(), cache, s.live_score_refresh_seconds, min_call_interval=0.0)
    service.poller_active = s.live_poller == "worker" and shared
    return service
