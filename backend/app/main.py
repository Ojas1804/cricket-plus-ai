import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1 import analytics, dashboard, matches, players, prompts, widgets
from app.core.config import get_settings
from app.core.exceptions import CricketCanvasError
from app.core.logging import configure_logging
from app.live.polling import LivePoller
from app.live.service import get_live_service

configure_logging()
settings = get_settings()

@asynccontextmanager
async def lifespan(_: FastAPI):
    task = None
    if settings.live_poller == "embedded":
        try:
            task = asyncio.create_task(LivePoller(get_live_service()).run_forever())
        except ValueError:
            task = None
    yield
    if task:
        task.cancel()


app = FastAPI(title="Cricket Canvas API", version="1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(prompts.router, prefix="/api/v1")
app.include_router(widgets.router, prefix="/api/v1")
app.include_router(analytics.router, prefix="/api/v1")
app.include_router(players.router, prefix="/api/v1")
app.include_router(matches.router, prefix="/api/v1")
app.include_router(dashboard.router, prefix="/api/v1")


@app.exception_handler(CricketCanvasError)
async def handle_app_error(_: Request, exc: CricketCanvasError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": str(exc)})


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
