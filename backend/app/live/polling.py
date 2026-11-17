import asyncio
import logging

from app.live.service import LiveService

logger = logging.getLogger(__name__)

MAX_BACKOFF_SECONDS = 600


def next_delay(refresh_seconds: int, failures: int, cap: int = MAX_BACKOFF_SECONDS) -> float:
    """Normal cadence while healthy; exponential backoff (capped) after consecutive failures."""
    return float(refresh_seconds) if failures == 0 else float(min(refresh_seconds * 2 ** min(failures, 10), cap))


class LivePoller:
    def __init__(self, service: LiveService) -> None:
        self.service = service
        self.failures = 0

    async def run_forever(self) -> None:
        self.service.poller_active = True
        while True:
            try:
                ok = await asyncio.to_thread(self.service.refresh_all)
            except Exception as e:
                logger.error("Live poll crashed: %s", type(e).__name__)
                ok = False
            self.failures = 0 if ok else self.failures + 1
            await asyncio.sleep(next_delay(self.service.refresh_seconds, self.failures))
