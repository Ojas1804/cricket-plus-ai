"""Deterministic cricket statistics. Ratios with a zero denominator return None (undefined), never 0."""

NON_BOWLER_WICKETS = frozenset({"run out", "retired hurt", "retired out", "obstructing the field"})
NON_DISMISSAL_KINDS = frozenset({"retired hurt"})
BALLS_PER_OVER = 6


def _ratio(numerator: float, denominator: float, scale: float = 1.0, digits: int = 2) -> float | None:
    return round(numerator / denominator * scale, digits) if denominator else None


def batting_average(runs: int, dismissals: int) -> float | None:
    return _ratio(runs, dismissals)


def batting_strike_rate(runs: int, balls_faced: int) -> float | None:
    return _ratio(runs, balls_faced, 100)


def bowling_economy(runs_conceded: int, legal_balls: int) -> float | None:
    return _ratio(runs_conceded, legal_balls, BALLS_PER_OVER)


def bowling_average(runs_conceded: int, wickets: int) -> float | None:
    return _ratio(runs_conceded, wickets)


def bowling_strike_rate(legal_balls: int, wickets: int) -> float | None:
    return _ratio(legal_balls, wickets)


def win_percentage(wins: int, matches: int) -> float | None:
    return _ratio(wins, matches, 100)


def average_per_innings(runs: int, innings: int) -> float | None:
    return _ratio(runs, innings)


def run_rate(runs: int, legal_balls: int) -> float | None:
    return _ratio(runs, legal_balls, BALLS_PER_OVER)


def overs_notation(legal_balls: int) -> str:
    return f"{legal_balls // BALLS_PER_OVER}.{legal_balls % BALLS_PER_OVER}"


def is_legal_delivery(extras: dict | None) -> bool:
    return not (extras and ("wides" in extras or "noballs" in extras))


def runs_charged_to_bowler(runs_total: int, extras: dict | None) -> int:
    """Byes, leg byes and penalty runs are not charged to the bowler."""
    extras = extras or {}
    return runs_total - sum(extras.get(k, 0) for k in ("byes", "legbyes", "penalty"))


def is_bowler_wicket(kind: str) -> bool:
    return kind not in NON_BOWLER_WICKETS


def is_batting_dismissal(kind: str) -> bool:
    return kind not in NON_DISMISSAL_KINDS


def batter_faced_ball(extras: dict | None) -> bool:
    """Wides are not balls faced; no-balls are."""
    return not (extras and "wides" in extras)
