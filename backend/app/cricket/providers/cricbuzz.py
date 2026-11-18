"""Cricbuzz live-score provider.

Uses Cricbuzz's unofficial public match-centre JSON (mcenter/comm and mcenter/scorecard). It has no contract, so
every payload is read defensively and any unexpected shape surfaces as a ProviderError. Match discovery scrapes
match ids from the live-scores page. Provides ball-by-ball over summaries and the current partnership.
"""
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from app.cricket.providers.base import LiveScoreProvider, ProviderError
from app.cricket.providers.cricapi import LIMITED_OVERS
from app.live.models import (
    BatterLine,
    BowlerLine,
    InningsScore,
    LiveMatch,
    MatchSummary,
    OverSummary,
    Partnership,
)

logger = logging.getLogger(__name__)

BASE_URL = "https://www.cricbuzz.com"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
UPCOMING_STATES = {"preview", "upcoming"}
COMPLETED_STATES = {"complete", "completed", "abandon", "abandoned", "no result"}
MAX_CANDIDATES = 25


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(str(value).replace(",", "")))
    except (TypeError, ValueError):
        return default


def _as_float(value: Any) -> float | None:
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _balls_from_overs(value: Any) -> int:
    """Cricket overs notation: 18.4 is 18 overs and 4 balls (Cricbuzz may also send 40.6)."""
    try:
        overs = float(value)
    except (TypeError, ValueError):
        return 0
    whole = int(overs)
    return whole * 6 + int(round((overs - whole) * 10))


def _overs_text(total_balls: int) -> str:
    whole, balls = divmod(total_balls, 6)
    return f"{whole}.{balls}"


def _status(header: dict[str, Any]) -> str:
    state = str(header.get("state") or "").strip().lower()
    if header.get("complete") or state in COMPLETED_STATES:
        return "COMPLETED"
    if state in UPCOMING_STATES:
        return "UPCOMING"
    return "LIVE"


def _teams(header: dict[str, Any]) -> list[str]:
    return [str(t["name"]) for t in (_dict(header.get("team1")), _dict(header.get("team2"))) if t.get("name")]


def _title(header: dict[str, Any]) -> str:
    teams = _teams(header)
    desc = str(header.get("matchDescription") or "").strip()
    base = " vs ".join(teams) or "Cricket match"
    return f"{base}, {desc}" if desc else base


def _format(header: dict[str, Any]) -> str:
    return str(header.get("matchFormat") or "UNKNOWN").upper()


def _is_not_out(out_desc: str) -> bool:
    return out_desc.strip().lower() in {"", "batting", "not out"}


def _batting_lines(rows: Any, striker_id: int | None) -> list[BatterLine]:
    lines = []
    for row in _dict(rows).values():
        row = _dict(row)
        name = str(row.get("batName") or "").strip()
        out_desc = str(row.get("outDesc") or "").strip()
        if not name or (not out_desc and not _as_int(row.get("balls")) and not _as_int(row.get("runs"))):
            continue
        lines.append(BatterLine(
            player=name,
            runs=_as_int(row.get("runs")),
            balls=_as_int(row.get("balls")),
            fours=_as_int(row.get("fours")),
            sixes=_as_int(row.get("sixes")),
            strike_rate=_as_float(row.get("strikeRate")),
            on_strike=striker_id is not None and _as_int(row.get("batId"), -1) == striker_id and _is_not_out(out_desc),
            dismissal="not out" if _is_not_out(out_desc) else out_desc,
        ))
    return lines


def _bowling_lines(rows: Any) -> list[BowlerLine]:
    lines = []
    for row in _dict(rows).values():
        row = _dict(row)
        name = str(row.get("bowlName") or "").strip()
        if not name:
            continue
        balls = _as_int(row.get("balls")) or _balls_from_overs(row.get("overs"))
        lines.append(BowlerLine(
            player=name,
            overs=_overs_text(balls),
            maidens=_as_int(row.get("maidens")),
            runs=_as_int(row.get("runs")),
            wickets=_as_int(row.get("wickets")),
            economy=_as_float(row.get("economy")),
        ))
    return lines


def _fall_of_wickets(rows: Any) -> list[str]:
    ordered = sorted((_dict(r) for r in _dict(rows).values()), key=lambda r: _as_int(r.get("wktNbr")))
    return [f"{_as_int(r.get('wktRuns'))}-{_as_int(r.get('wktNbr'))} ({r.get('batName')}, {r.get('wktOver')} ov)"
            for r in ordered if r.get("batName")]


def _recent_overs(commentary: Any, innings_id: int) -> list[OverSummary]:
    overs: dict[int, OverSummary] = {}
    for item in _dict(commentary).values():
        sep = _dict(_dict(item).get("overSeparator"))
        if _as_int(_dict(item).get("inningsId")) != innings_id or not sep.get("overNumber"):
            continue
        number = _as_int(sep["overNumber"])
        overs[number] = OverSummary(over=number, balls=str(sep.get("overSummary") or "").split(),
                                    runs=_as_int(sep.get("overRuns")))
    return [overs[n] for n in sorted(overs)][-3:]


class CricbuzzProvider:
    name = "cricbuzz"
    is_mock = False

    def __init__(self, base_url: str = BASE_URL, timeout: float = 15.0, client: httpx.Client | None = None,
                 cache_seconds: float = 3.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(timeout=timeout, headers={"User-Agent": USER_AGENT}, follow_redirects=True)
        self._owns_client = client is None
        self._cache_seconds = cache_seconds
        self._cache: dict[str, tuple[float, Any]] = {}

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _fetch(self, path: str) -> httpx.Response:
        try:
            response = self._client.get(f"{self._base_url}/{path}")
        except httpx.HTTPError as e:
            raise ProviderError("Cricbuzz request failed") from e
        if response.status_code != 200:
            raise ProviderError(f"Cricbuzz returned HTTP {response.status_code}")
        return response

    def _json(self, path: str) -> dict[str, Any]:
        cached = self._cache.get(path)
        if cached and time.monotonic() - cached[0] < self._cache_seconds:
            return cached[1]
        try:
            payload = self._fetch(path).json()
        except ValueError as e:
            raise ProviderError("Cricbuzz returned invalid JSON") from e
        if not isinstance(payload, dict):
            raise ProviderError("Cricbuzz returned an unexpected payload")
        self._cache[path] = (time.monotonic(), payload)
        return payload

    def _comm(self, match_id: str) -> dict[str, Any]:
        return self._json(f"api/mcenter/comm/{match_id}")

    def list_live_matches(self) -> list[MatchSummary]:
        html = self._fetch("cricket-match/live-scores").text
        ids = list(dict.fromkeys(re.findall(r"/live-cricket-scores/(\d+)/", html)))[:MAX_CANDIDATES]
        matches = []
        for match_id in ids:
            try:
                header = _dict(self._comm(match_id).get("matchHeader"))
            except ProviderError as e:
                logger.warning("Cricbuzz header fetch failed for %s: %s", match_id, e)
                continue
            if _status(header) != "LIVE":
                continue
            matches.append(MatchSummary(match_id=match_id, title=_title(header), format=_format(header), status="LIVE"))
        return matches

    def get_scorecard(self, match_id: str) -> LiveMatch:
        comm = self._comm(match_id)
        card = self._json(f"api/mcenter/scorecard/{match_id}")
        try:
            return self._to_live_match(comm, card, match_id)
        except (KeyError, TypeError, ValueError, AttributeError) as e:
            raise ProviderError("Cricbuzz returned an unexpected scorecard") from e

    def _to_live_match(self, comm: dict[str, Any], card: dict[str, Any], match_id: str) -> LiveMatch:
        header = _dict(comm.get("matchHeader")) or _dict(card.get("matchHeader"))
        mini = _dict(comm.get("miniscore"))
        status = _status(header)
        fmt = _format(header)
        raw_innings = [_dict(i) for i in card.get("scoreCard") or [] if isinstance(i, dict)]
        count = len(raw_innings)
        current_id = _as_int(mini.get("inningsId"))
        striker_id = _as_int(_dict(mini.get("batsmanStriker")).get("id"), -1)

        innings: list[InningsScore] = []
        for index, raw in enumerate(raw_innings, start=1):
            score = _dict(raw.get("scoreDetails"))
            bat = _dict(raw.get("batTeamDetails"))
            legal_balls = _as_int(score.get("ballNbr")) or _balls_from_overs(score.get("overs"))
            wickets = _as_int(score.get("wickets"))
            limit = LIMITED_OVERS.get(fmt)
            is_current = status == "LIVE" and index == count
            completed = (status == "COMPLETED" or index < count or wickets >= 10 or bool(score.get("declared"))
                         or (limit is not None and legal_balls >= limit))
            innings.append(InningsScore(
                number=index,
                team=str(bat.get("batTeamName") or "Unknown"),
                runs=_as_int(score.get("runs")),
                wickets=wickets,
                overs=_overs_text(legal_balls),
                legal_balls=legal_balls,
                completed=completed,
                batting=_batting_lines(bat.get("batsmenData"), striker_id if is_current and not completed else None),
                bowling=_bowling_lines(_dict(raw.get("bowlTeamDetails")).get("bowlersData")),
                fall_of_wickets=_fall_of_wickets(raw.get("wicketsData")),
            ))

        last = innings[-1] if innings else None
        target = runs_required = balls_remaining = required_run_rate = partnership = None
        recent_overs: list[OverSummary] = []
        if status == "LIVE" and last:
            mini_target = _as_int(mini.get("target"))
            if mini_target > 0 and current_id == last.number:
                target = mini_target
                runs_required = max(0, mini_target - last.runs)
                if fmt in LIMITED_OVERS:
                    balls_remaining = max(0, LIMITED_OVERS[fmt] - last.legal_balls)
                required_run_rate = _as_float(mini.get("requiredRunRate")) or None
            pship = _dict(mini.get("partnerShip"))
            if pship and current_id == last.number:
                batters = [str(_dict(mini.get(k)).get("name")) for k in ("batsmanStriker", "batsmanNonStriker")
                           if _dict(mini.get(k)).get("name")]
                partnership = Partnership(runs=_as_int(pship.get("runs")), balls=_as_int(pship.get("balls")), batters=batters)
            recent_overs = _recent_overs(comm.get("matchCommentary"), last.number)

        venue = _dict(header.get("venue"))
        venue_text = ", ".join(str(venue[k]) for k in ("name", "city") if venue.get(k)) or None
        return LiveMatch(
            match_id=str(header.get("matchId") or match_id),
            title=_title(header),
            format=fmt,
            status=status,  # type: ignore[arg-type]
            status_text=str(header.get("status") or "Match status unavailable"),
            teams=_teams(header),
            venue=venue_text,
            current_innings=count if status != "UPCOMING" and count else None,
            innings=innings,
            current_run_rate=round(last.runs / last.legal_balls * 6, 2) if last and last.legal_balls else None,
            required_run_rate=required_run_rate,
            target=target,
            runs_required=runs_required,
            balls_remaining=balls_remaining,
            partnership=partnership,
            recent_overs=recent_overs,
            updated_at=datetime.now(timezone.utc),
        )
