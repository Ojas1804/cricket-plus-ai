"""CricAPI live-score provider.

Maps CricAPI's currentMatches and match_scorecard responses to the normalized live models.
The provider does not expose ball-by-ball data, so recent overs and partnerships are unavailable.
"""
import re
from datetime import datetime, timezone
from typing import Any

import httpx

from app.cricket.providers.base import LiveScoreProvider, ProviderError
from app.live.models import (
    BatterLine,
    BowlerLine,
    InningsScore,
    LiveMatch,
    MatchSummary,
)

LIMITED_OVERS = {"T20": 120, "ODI": 300, "T10": 60}


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


def _overs_parts(value: Any) -> tuple[int, str]:
    """CricAPI uses cricket overs notation: 18.4 means 18 overs and 4 balls."""
    match = re.search(r"\d+(?:\.\d+)?", str(value or ""))
    if not match:
        return 0, "0.0"
    overs = float(match.group(0))
    whole = int(overs)
    balls = int(round((overs - whole) * 10))
    if balls >= 10:
        whole += balls // 10
        balls %= 10
    total_balls = whole * 6 + balls
    whole, balls = divmod(total_balls, 6)
    return total_balls, f"{whole}.{balls}"


def _overs_text(value: Any) -> str:
    return _overs_parts(value)[1]


def _person_name(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("name") or "").strip()
    return str(value or "").strip()


def _format(match: dict[str, Any]) -> str:
    name = str(match.get("name") or "").lower()
    status = str(match.get("status") or "").lower()
    match_type = str(match.get("matchType") or "").lower()
    if "t10" in name or match_type == "t10":
        return "T10"
    if "test" in name or status.startswith("day "):
        return "TEST"
    if "odi" in name or "one day" in name or "list a" in name:
        return "ODI"
    if "t20" in name or match_type in {"t20", "t20i"}:
        return "T20"
    return match_type.upper() or "UNKNOWN"


def _status(data: dict[str, Any], has_scores: bool) -> str:
    if data.get("matchEnded"):
        return "COMPLETED"
    if data.get("matchStarted") or has_scores or data.get("scorecard"):
        return "LIVE"
    return "UPCOMING"


def _batting_team(label: str, teams: list[str], previous_team: str | None, index: int) -> str:
    prefix = re.split(r"\s+inning\s+\d+", label, maxsplit=1, flags=re.IGNORECASE)[0] if label else ""
    candidates = [team for team in teams if team and team.lower() in prefix.lower()]
    if len(candidates) > 1:
        others = [team for team in candidates if team != previous_team]
        if len(others) == 1:
            return others[0]
        return candidates[-1]
    if candidates:
        return candidates[0]
    if previous_team and previous_team in teams:
        others = [team for team in teams if team != previous_team]
        if len(others) == 1:
            return others[0]
    return teams[index % len(teams)] if teams else "Unknown"


def _is_not_out(row: dict[str, Any]) -> bool:
    dismissal = str(row.get("dismissal") or "").strip().lower()
    text = str(row.get("dismissal-text") or "").strip().lower()
    return dismissal in {"", "not out"} and text in {"", "not out", "batting"}


def _dismissal(row: dict[str, Any]) -> str:
    text = str(row.get("dismissal-text") or "").strip()
    if text:
        return "not out" if text.lower() in {"batting", "not out"} else text
    dismissal = str(row.get("dismissal") or "").strip()
    if dismissal:
        return "not out" if dismissal.lower() == "not out" else dismissal
    return "not out"


def _batting_lines(rows: Any, allow_striker: bool) -> list[BatterLine]:
    entries: list[tuple[BatterLine, bool]] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        name = _person_name(row.get("batsman"))
        if not name:
            continue
        line = BatterLine(
            player=name,
            runs=_as_int(row.get("r")),
            balls=_as_int(row.get("b")),
            fours=_as_int(row.get("4s")),
            sixes=_as_int(row.get("6s")),
            strike_rate=_as_float(row.get("sr")),
            dismissal=_dismissal(row),
        )
        entries.append((line, _is_not_out(row)))
    if allow_striker:
        for line, not_out in reversed(entries):
            if not_out:
                line.on_strike = True
                break
    return [line for line, _ in entries]


def _bowling_lines(rows: Any) -> list[BowlerLine]:
    lines = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        name = _person_name(row.get("bowler"))
        if not name:
            continue
        lines.append(BowlerLine(
            player=name,
            overs=_overs_text(row.get("o")),
            maidens=_as_int(row.get("m")),
            runs=_as_int(row.get("r")),
            wickets=_as_int(row.get("w")),
            economy=_as_float(row.get("eco")),
        ))
    return lines


def _innings_completed(score: dict[str, Any], fmt: str) -> bool:
    if _as_int(score.get("w")) >= 10:
        return True
    max_balls = LIMITED_OVERS.get(fmt)
    return max_balls is not None and _overs_parts(score.get("o"))[0] >= max_balls


def _innings(index: int, team: str, score: dict[str, Any], card: dict[str, Any], fmt: str,
             match_completed: bool, is_current_live: bool) -> InningsScore:
    legal_balls, overs = _overs_parts(score.get("o"))
    completed = match_completed or _innings_completed(score, fmt)
    return InningsScore(
        number=index,
        team=team,
        runs=_as_int(score.get("r")),
        wickets=_as_int(score.get("w")),
        overs=overs,
        legal_balls=legal_balls,
        completed=completed,
        batting=_batting_lines(card.get("batting"), allow_striker=is_current_live and not completed),
        bowling=_bowling_lines(card.get("bowling")),
    )


class CricApiProvider:
    name = "cricapi"
    is_mock = False

    def __init__(self, api_key: str, base_url: str = "https://api.cricapi.com/v1", timeout: float = 20.0,
                 client: httpx.Client | None = None) -> None:
        self._api_key = api_key.strip()
        if not self._api_key:
            raise ValueError("CricAPI api_key is required")
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(timeout=timeout)
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _get(self, path: str, **params: Any) -> Any:
        try:
            response = self._client.get(
                f"{self._base_url}/{path}",
                params={"apikey": self._api_key, "offset": 0, **params},
            )
        except httpx.HTTPError as e:
            raise ProviderError("CricAPI request failed") from e
        if response.status_code != 200:
            raise ProviderError(f"CricAPI returned HTTP {response.status_code}")
        try:
            payload = response.json()
        except ValueError as e:
            raise ProviderError("CricAPI returned invalid JSON") from e
        if not isinstance(payload, dict) or str(payload.get("status") or "").lower() != "success":
            reason = payload.get("reason") if isinstance(payload, dict) else None
            reason = str(reason or "request failed").replace(self._api_key, "[redacted]")
            raise ProviderError(f"CricAPI error: {reason}")
        return payload.get("data")

    def list_live_matches(self) -> list[MatchSummary]:
        data = self._get("currentMatches")
        matches = []
        for item in data if isinstance(data, list) else []:
            if not isinstance(item, dict) or not item.get("id"):
                continue
            if item.get("matchEnded") or item.get("matchStarted") is False:
                continue
            teams = [str(t) for t in item.get("teams") or [] if t]
            title = str(item.get("name") or " vs ".join(teams) or "Cricket match")
            matches.append(MatchSummary(
                match_id=str(item["id"]),
                title=title,
                format=_format(item),
                status="LIVE",
            ))
        return matches

    def get_scorecard(self, match_id: str) -> LiveMatch:
        data = self._get("match_scorecard", id=match_id)
        if not isinstance(data, dict):
            raise ProviderError("CricAPI returned an invalid scorecard")
        return self._to_live_match(data, match_id)

    def _to_live_match(self, data: dict[str, Any], match_id: str) -> LiveMatch:
        teams = [str(t) for t in data.get("teams") or [] if t]
        if not teams:
            teams = [str(t.get("name")) for t in data.get("teamInfo") or [] if isinstance(t, dict) and t.get("name")]
        scores = [s for s in data.get("score") or [] if isinstance(s, dict)]
        cards = [c for c in data.get("scorecard") or [] if isinstance(c, dict)]
        count = max(len(scores), len(cards))
        fmt = _format(data)
        status = _status(data, bool(scores or cards))
        match_completed = status == "COMPLETED"

        innings: list[InningsScore] = []
        previous_team = None
        for i in range(count):
            score = scores[i] if i < len(scores) else {}
            card = cards[i] if i < len(cards) else {}
            label = str(card.get("inning") or score.get("inning") or "")
            team = _batting_team(label, teams, previous_team, i)
            is_current_live = status == "LIVE" and i == count - 1
            innings.append(_innings(i + 1, team, score, card, fmt, match_completed, is_current_live))
            previous_team = team

        target = runs_required = balls_remaining = required_run_rate = None
        current_runs = legal_balls = 0
        if innings:
            last_score = scores[-1] if scores else {}
            current_runs = _as_int(last_score.get("r"))
            legal_balls = _overs_parts(last_score.get("o"))[0]
        if status == "LIVE" and fmt in LIMITED_OVERS and len(scores) >= 2:
            target = _as_int(scores[0].get("r")) + 1
            balls_remaining = max(0, LIMITED_OVERS[fmt] - legal_balls)
            runs_required = max(0, target - current_runs)
            if balls_remaining > 0 and runs_required > 0:
                required_run_rate = round(runs_required / balls_remaining * 6, 2)

        return LiveMatch(
            match_id=str(data.get("id") or match_id),
            title=str(data.get("name") or "Cricket match"),
            format=fmt,
            status=status,  # type: ignore[arg-type]
            status_text=str(data.get("status") or "Match status unavailable"),
            teams=teams,
            venue=str(data.get("venue")) if data.get("venue") else None,
            current_innings=count if status != "UPCOMING" and count else None,
            innings=innings,
            current_run_rate=round(current_runs / legal_balls * 6, 2) if legal_balls else None,
            required_run_rate=required_run_rate,
            target=target,
            runs_required=runs_required,
            balls_remaining=balls_remaining,
            recent_overs=[],
            updated_at=datetime.now(timezone.utc),
        )
