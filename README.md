# Cricket Canvas

Prompt-first, AI-powered cricket analytics workspace. See `writing-block.md` for the PRD and architecture.

## Run with Docker

    cp .env.example .env
    docker compose up --build

- Frontend: http://localhost:5173
- Backend: http://localhost:8000/docs
- PostgreSQL is exposed on `localhost:5433` and Redis on `localhost:6380` to avoid conflicts with local services.
  Containers still use the standard internal ports.
- The frontend calls `/api` on the same origin; Vite proxies it to the backend, so browser CORS is not involved.

Database migrations run automatically before the backend and worker start. Useful commands:

    docker compose logs -f backend frontend
    docker compose down

## Develop without Docker

    cd backend && python -m venv .venv && .venv/Scripts/activate && pip install -r requirements.txt
    uvicorn app.main:app --reload

    cd frontend && npm install && npm run dev

Currently the backend returns mock widgets (Milestone 1). Historical ingestion will be a separate command.

## Historical data (Milestone 2)

Ingestion is a separate command and never runs on startup. Download Cricsheet JSON (https://cricsheet.org/downloads/) into `data/raw/`.

With Docker Compose, migrations have already run and `data/` is mounted at `/data`:

    docker compose exec backend python -m app.cricket.ingestion.cricsheet /data/raw/ipl_json.zip   # or /data/raw directory

Without Docker, from `backend/`:

    alembic upgrade head
    python -m app.cricket.ingestion.cricsheet ../data/raw/ipl_json.zip   # or a directory of .json files

Without `DATABASE_URL`, the local backend uses SQLite (`data/cricket.db`). Docker Compose uses PostgreSQL.

Query it through the restricted DSL: `POST /api/v1/analytics/query` (see `backend/app/analytics/query_dsl.py`).
Cricsheet carries no venue country, so `venue_country` filters return a coverage warning until that data is added.

## Splits, geography and linked widgets (Milestone 4)

- Group or filter by `opposition`, `team`, `venue_country`, `competition`, `season`, `format` and `home_away`.
- Cricsheet has no venue country, so it is inferred from a curated city list at ingestion. For data ingested earlier run
  `python -m app.cricket.normalization.geography` from `backend/` to backfill. Unmapped venues stay unknown and are reported in widget warnings.
- `home` means the venue country equals the player's national team country; everything else (neutral venues included) is `away`.
  Club and franchise teams have no home country, so their matches are unclassified.
- Selecting a player row in a leaderboard or table emits `PLAYER_SELECTED`. Profile widgets follow it by default; chart and table widgets
  can opt in from their menu ("Link to selection"). Linking only swaps the player filter.

Team-level queries use the `team_results` dataset (one row per team per match): wins, losses, win percentage, runs scored and
conceded, average score, run rate and more, with the same splits (opposition, venue, venue country, home/away, season, format, competition).

## Live cricket (Milestone 5)

- Live data goes through the `LiveScoreProvider` interface and is normalized before it reaches the browser. Set
  `LIVE_SCORE_PROVIDER=cricapi` with `LIVE_SCORE_API_KEY` to use CricAPI (`LIVE_SCORE_BASE_URL` is optional), or keep
  `LIVE_SCORE_PROVIDER=mock` for the deterministic simulator (every live widget is labelled MOCK).
- CricAPI supplies match and innings scorecards but not ball-by-ball data, so recent overs and partnerships are unavailable
  for real matches. Check your CricAPI plan's daily quota and choose `LIVE_SCORE_REFRESH_SECONDS` accordingly.
- `LIVE_SCORE_PROVIDER=cricbuzz` needs no API key. It reads Cricbuzz's unofficial match-centre JSON, which has no contract and may
  change or be blocked, and it adds recent overs, the current partnership and the striker. Use it for personal or non-commercial
  use and check Cricbuzz's terms. Behind a TLS-inspecting proxy, point `SSL_CERT_FILE` at your CA bundle. Playing XI is not provided.
- The backend polls the provider about every `LIVE_SCORE_REFRESH_SECONDS` (default 60) and caches the result (Redis when reachable,
  in-process otherwise). Browsers only read the cache. Failures keep the last known score, mark it stale and back off exponentially (capped at 10 minutes).
- `LIVE_POLLER=embedded` polls inside the API process; with Docker Compose the `worker` service polls and the API reads Redis.
- Endpoints: `GET /api/v1/matches/live`, `/matches/{id}`, `/matches/{id}/scorecard`, `/matches/{id}/widget`.
- Prompts such as "show all live matches" skip the LLM and create one independently refreshing scorecard per live match.

## Persistence, history and export (Milestone 6)

- The dashboard (widgets, layout, expanded/collapsed and link state) and the last 50 queries are saved in the browser's IndexedDB
  and restored on load. Restored widgets are re-attached to the backend through `POST /api/v1/dashboard/widgets`, so refresh, update and
  linking keep working after a backend restart. Transient states (loading, errors) are not restored.
- Widget menu: Export JSON (full spec) and Export CSV (data preceded by `#` comment lines with source, filters, coverage, metric definitions
  and warnings; mock data is flagged). The header has Export dashboard. Press the up/down arrow in the prompt box to recall earlier queries.
- Analytics results are cached for `ANALYTICS_CACHE_TTL_SECONDS` (default 600, 0 disables) in Redis or memory. New ingestions invalidate the
  cache automatically and widget refresh bypasses it. Cached results are flagged in provenance.
- Extra chart types: radar (multi-metric profiles) and heatmap (one metric across two splits), alongside line, bar, pie and scatter.
- Layouts adapt: 12 columns on desktop, 6 on tablets, stacked on phones. Only desktop arrangements are saved.
