"""ESPNcricinfo live-score provider backed by the `cricdata` package.

Match ids are "<seriesObjectId>-<matchObjectId>" because cricdata needs both. The library is synchronous and slow
(seconds per call), so use it from the poller only. Behind a TLS-inspecting proxy set CURL_CA_BUNDLE to a CA bundle.
"""
import logging
import re
from datetime import datetime, timezone
from typing import Any

from app.cricket.providers.base import ProviderError
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

ID_PATTERN = re.compile(r"^\d+-\d+$")
PLACEHOLDER = re.compile(r"\{\{.*?\}\}")


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


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
    try:
        overs = float(value)
    except (TypeError, ValueError):
        return 0
    whole = int(overs)
    return whole * 6 + int(round((overs - whole) * 10))


def _overs_text(total_balls: int) -> str:
    whole, balls = divmod(total_balls, 6)
    return f"{whole}.{balls}"


def _status(match: dict[str, Any]) -> str:
    state = str(match.get("state") or "").upper()
    if match.get("isCancelled"):
        return "COMPLETED"
    return {"LIVE": "LIVE", "PRE": "UPCOMING"}.get(state, "COMPLETED")


def _team_names(match: dict[str, Any]) -> list[str]:
    names = [str(_dict(_dict(t).get("team")).get("name") or "") for t in _list(match.get("teams"))]
    return [n for n in names if n]


def _title(match: dict[str, Any]) -> str:
    base = " vs ".join(_team_names(match)) or "Cricket match"
    extra = str(match.get("title") or "").strip()
    return f"{base}, {extra}" if extra else base


def _ball_token(ball: dict[str, Any]) -> str:
    if ball.get("isWicket"):
        return "W"
    if _as_int(ball.get("wides")):
        return "Wd"
    if _as_int(ball.get("noballs")):
        return "Nb"
    return str(_as_int(ball.get("totalRuns")))


def _dismissal(row: dict[str, Any]) -> str:
    text = _dict(row.get("dismissalText"))
    return str(text.get("long") or text.get("short") or "out").strip()


def _striker_id(innings: dict[str, Any]) -> int | None:
    """The batter on strike after the latest delivery, assuming ordinary strike rotation."""
    balls = [b for over in _list(innings.get("inningOvers")) for b in _list(_dict(over).get("balls")) if isinstance(b, dict)]
    if not balls or balls[-1].get("isWicket"):
        return None
    last = balls[-1]
    striker, non_striker = last.get("batsmanPlayerId"), last.get("nonStrikerPlayerId")
    legal = not (_as_int(last.get("wides")) or _as_int(last.get("noballs")))
    ran = _as_int(last.get("batsmanRuns")) + _as_int(last.get("byes")) + _as_int(last.get("legbyes"))
    if ran % 2 == 1:
        striker, non_striker = non_striker, striker
    if legal and _as_int(last.get("ballNumber")) == 6:
        striker, non_striker = non_striker, striker
    return _as_int(striker, -1) if striker is not None else None


class CricdataProvider:
    name = "cricdata"
    is_mock = False

    def __init__(self, client: Any = None, timeout: int = 25) -> None:
        if client is None:
            from cricdata import CricinfoClient

            client = CricinfoClient(timeout=timeout)
        self._client = client

    @staticmethod
    def accepts_id(match_id: str) -> bool:
        return bool(ID_PATTERN.match(match_id))

    def list_live_matches(self) -> list[MatchSummary]:
        try:
            raw = self._client.live_matches()
        except Exception as e:
            raise ProviderError("Cricdata request failed") from e
        matches = []
        for item in raw if isinstance(raw, list) else []:
            item = _dict(item)
            series_id, match_id = _dict(item.get("series")).get("objectId"), item.get("objectId")
            if _status(item) != "LIVE" or not series_id or not match_id:
                continue
            matches.append(MatchSummary(match_id=f"{series_id}-{match_id}", title=_title(item),
                                        format=str(item.get("format") or "UNKNOWN").upper(), status="LIVE"))
        return matches

    def get_scorecard(self, match_id: str) -> LiveMatch:
        if not self.accepts_id(match_id):
            raise ProviderError(f"Invalid cricdata match id '{match_id}'")
        series_id, object_id = match_id.split("-")
        try:
            data = self._client.match_scorecard(f"series-{series_id}", f"match-{object_id}")
        except Exception as e:
            raise ProviderError("Cricdata request failed") from e
        try:
            return self._to_live_match(_dict(data), match_id)
        except (KeyError, TypeError, ValueError, AttributeError) as e:
            raise ProviderError("Cricdata returned an unexpected scorecard") from e

    def _to_live_match(self, data: dict[str, Any], match_id: str) -> LiveMatch:
        match = _dict(data.get("match"))
        content = _dict(data.get("content"))
        status = _status(match)
        fmt = str(match.get("format") or "UNKNOWN").upper()
        raw_innings = [_dict(i) for i in _list(content.get("innings")) if _dict(i).get("isBatted")]
        count = len(raw_innings)

        innings: list[InningsScore] = []
        for index, raw in enumerate(raw_innings):
            balls = _as_int(raw.get("balls")) or _balls_from_overs(raw.get("overs"))
            wickets = _as_int(raw.get("wickets"))
            limit = LIMITED_OVERS.get(fmt)
            is_current = status == "LIVE" and index == count - 1 and bool(raw.get("isCurrent"))
            completed = (status == "COMPLETED" or not raw.get("isCurrent") or wickets >= 10
                         or (limit is not None and balls >= (_as_int(raw.get("totalBalls")) or limit)))
            striker = _striker_id(raw) if is_current and not completed else None
            batting, did_not_bat = [], []
            for row in _list(raw.get("inningBatsmen")):
                row = _dict(row)
                player = _dict(row.get("player"))
                name = str(player.get("name") or "").strip()
                if not name:
                    continue
                if row.get("battedType") != "yes":
                    did_not_bat.append(name)
                    continue
                out = bool(row.get("isOut"))
                batting.append(BatterLine(
                    player=name, runs=_as_int(row.get("runs")), balls=_as_int(row.get("balls")),
                    fours=_as_int(row.get("fours")), sixes=_as_int(row.get("sixes")),
                    strike_rate=_as_float(row.get("strikerate")),
                    on_strike=not out and striker is not None and _as_int(player.get("id"), -2) == striker,
                    dismissal=_dismissal(row) if out else "not out",
                ))
            bowling = []
            for row in _list(raw.get("inningBowlers")):
                row = _dict(row)
                name = str(_dict(row.get("player")).get("name") or "").strip()
                if name and row.get("bowledType") == "yes":
                    b = _as_int(row.get("balls")) or _balls_from_overs(row.get("overs"))
                    bowling.append(BowlerLine(
                        player=name, overs=_overs_text(b), maidens=_as_int(row.get("maidens")),
                        runs=_as_int(row.get("conceded")), wickets=_as_int(row.get("wickets")),
                        economy=_as_float(row.get("economy"))))
            fows = []
            for row in _list(raw.get("inningFallOfWickets")):
                row = _dict(row)
                name = _dict(row.get("dismissalBatsman")).get("name")
                if name:
                    fows.append(f"{_as_int(row.get('fowRuns'))}-{_as_int(row.get('fowWicketNum'))} ({name}, {row.get('fowOvers')} ov)")
            innings.append(InningsScore(
                number=_as_int(raw.get("inningNumber"), index + 1), team=str(_dict(raw.get("team")).get("name") or "Unknown"),
                runs=_as_int(raw.get("runs")), wickets=wickets, overs=_overs_text(balls), legal_balls=balls,
                completed=completed, batting=batting, bowling=bowling, fall_of_wickets=fows, did_not_bat=did_not_bat))

        last_raw = raw_innings[-1] if raw_innings else {}
        last = innings[-1] if innings else None
        target = runs_required = balls_remaining = required_run_rate = partnership = None
        recent_overs: list[OverSummary] = []
        if status == "LIVE" and last and not last.completed:
            overs = [_dict(o) for o in _list(last_raw.get("inningOvers"))]
            latest = overs[-1] if overs else {}
            if _as_int(last_raw.get("target")) > 0:
                target = _as_int(last_raw["target"])
                runs_required = _as_int(latest.get("requiredRuns"), max(0, target - last.runs))
                required_run_rate = _as_float(latest.get("requiredRunRate"))
                if fmt in LIMITED_OVERS:
                    balls_remaining = _as_int(latest.get("remainingBalls"),
                                              max(0, (_as_int(last_raw.get("totalBalls")) or LIMITED_OVERS[fmt]) - last.legal_balls))
            fow_rows = [_dict(f) for f in _list(last_raw.get("inningFallOfWickets"))]
            last_fow = fow_rows[-1] if fow_rows else {}
            pship_balls = last.legal_balls - _balls_from_overs(last_fow.get("fowOvers"))
            at_crease = [b for b in last.batting if b.dismissal == "not out"]
            if at_crease and pship_balls >= 0:
                partnership = Partnership(runs=last.runs - _as_int(last_fow.get("fowRuns")), balls=pship_balls,
                                          batters=[b.player for b in sorted(at_crease, key=lambda b: not b.on_strike)])
            recent_overs = [OverSummary(over=_as_int(o.get("overNumber")), runs=_as_int(o.get("overRuns")),
                                        balls=[_ball_token(_dict(b)) for b in _list(o.get("balls"))])
                            for o in overs if _list(o.get("balls"))][-3:]

        status_text = PLACEHOLDER.sub("", str(match.get("statusText") or "")).strip()
        if not status_text or (status == "UPCOMING" and "{{" in str(match.get("statusText"))):
            status_text = "Match yet to begin" if status == "UPCOMING" else "Match status unavailable"
        return LiveMatch(
            match_id=match_id,
            title=_title(match),
            format=fmt,
            status=status,  # type: ignore[arg-type]
            status_text=status_text,
            teams=_team_names(match),
            venue=str(_dict(match.get("ground")).get("name") or "") or None,
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
