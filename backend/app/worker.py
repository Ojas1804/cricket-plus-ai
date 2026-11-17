import asyncio

from app.core.logging import configure_logging
from app.live.polling import LivePoller
from app.live.service import get_live_service


async def main() -> None:
    configure_logging()
    await LivePoller(get_live_service()).run_forever()


if __name__ == "__main__":
    asyncio.run(main())
