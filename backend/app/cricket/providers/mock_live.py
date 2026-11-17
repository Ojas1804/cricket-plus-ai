"""Deterministic simulated live matches for development. Everything produced here is mock data and is flagged as such."""
import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.cricket.providers.base import ProviderError
from app.live.models import (
    BatterLine, BowlerLine, InningsScore, LiveMatch, MatchSummary, OverSummary, Partnership,
)

SQUADS = {
    "India": ["Rohit Sharma", "Shubman Gill", "Virat Kohli", "Shreyas Iyer", "KL Rahul", "Hardik Pandya", "Ravindra Jadeja",
              "Kuldeep Yadav", "Mohammed Shami", "Jasprit Bumrah", "Mohammed Siraj"],
    "Australia": ["David Warner", "Travis Head", "Steve Smith", "Marnus Labuschagne", "Glenn Maxwell", "Mitchell Marsh", "Alex Carey",
                  "Pat Cummins", "Mitchell Starc", "Adam Zampa", "Josh Hazlewood"],
    "England": ["Jos Buttler", "Phil Salt", "Will Jacks", "Harry Brook", "Liam Livingstone", "Sam Curran", "Moeen Ali",
                "Chris Woakes", "Adil Rashid", "Jofra Archer", "Mark Wood"],
    "Pakistan": ["Babar Azam", "Mohammad Rizwan", "Fakhar Zaman", "Saim Ayub", "Iftikhar Ahmed", "Shadab Khan", "Imad Wasim",
                 "Shaheen Afridi", "Haris Rauf", "Naseem Shah", "Abrar Ahmed"],
}
WEIGHTS = {
    "T20": {"0": 28, "1": 30, "2": 7, "3": 1, "4": 14, "6": 7, "W": 4, "Wd": 3},
    "ODI": {"0": 34, "1": 33, "2": 7, "3": 1, "4": 11, "6": 4, "W": 2.2, "Wd": 2.5},
    "TEST": {"0": 56, "1": 24, "2": 4, "3": 1, "4": 6, "6": 1, "W": 1.8, "Wd": 0.5},
}
BALLS_PER_OVER = 6
TEST_BALLS_PER_DAY = 540


def _overs(balls: int) -> str:
    return f"{balls // BALLS_PER_OVER}.{balls % BALLS_PER_OVER}"


def _token_runs(token: str) -> int:
    return 1 if token == "Wd" else 0 if token == "W" else int(token)


@dataclass
class _Batter:
    name: str
    runs: int = 0
    balls: int = 0
    fours: int = 0
    sixes: int = 0
    dismissal: str | None = None


@dataclass
class _Bowler:
    name: str
    balls: int = 0
    runs: int = 0
    wickets: int = 0
    maidens: int = 0
    over_runs: int = 0


@dataclass
class _State:
    batters: list[_Batter]
    bowlers: dict[str, _Bowler]
    runs: int = 0
    wickets: int = 0
    legal: int = 0
    striker: int = 0
    non_striker: int = 1
    next_idx: int = 2
    partnership_runs: int = 0
    partnership_balls: int = 0
    fow: list[str] = field(default_factory=list)
    overs: list[list[str]] = field(default_factory=list)
    finished: bool = False


def _simulate(batting: list[str], bowling: list[str], fmt: str, seed: int, max_balls: int, limit: int, target: int | None) -> _State:
    rng = random.Random(seed)
    keys, weights = list(WEIGHTS[fmt]), list(WEIGHTS[fmt].values())
    st = _State([_Batter(n) for n in batting], {n: _Bowler(n) for n in bowling[6:11]})
    cycle = bowling[6:11]
    cap = min(max_balls, limit)

    def done() -> bool:
        return st.wickets >= 10 or st.legal >= max_balls or (target is not None and st.runs >= target)

    while st.legal < cap and not done():
        over_idx = st.legal // BALLS_PER_OVER
        bowler = st.bowlers[cycle[over_idx % len(cycle)]]
        if len(st.overs) <= over_idx:
            st.overs.append([])
        token = rng.choices(keys, weights)[0]
        st.overs[over_idx].append(token)
        if token == "Wd":
            st.runs += 1
            bowler.runs += 1
            bowler.over_runs += 1
            st.partnership_runs += 1
            continue
        striker = st.batters[st.striker]
        st.legal += 1
        striker.balls += 1
        bowler.balls += 1
        st.partnership_balls += 1
        if token == "W":
            striker.dismissal = f"b {bowler.name}"
            bowler.wickets += 1
            st.wickets += 1
            st.fow.append(f"{st.wickets}-{st.runs} ({striker.name}, {_overs(st.legal)} ov)")
            st.partnership_runs = st.partnership_balls = 0
            if st.wickets < 10:
                st.striker, st.next_idx = st.next_idx, st.next_idx + 1
        else:
            r = int(token)
            striker.runs += r
            striker.fours += r == 4
            striker.sixes += r == 6
            st.runs += r
            bowler.runs += r
            bowler.over_runs += r
            st.partnership_runs += r
            if r % 2:
                st.striker, st.non_striker = st.non_striker, st.striker
        if st.legal % BALLS_PER_OVER == 0:
            bowler.maidens += bowler.over_runs == 0
            bowler.over_runs = 0
            st.striker, st.non_striker = st.non_striker, st.striker
    st.finished = done()
    return st


def _innings_score(number: int, team: str, st: _State, batting: list[str]) -> InningsScore:
    batted = st.batters[: min(st.next_idx, len(st.batters))]
    lines = []
    for i, b in enumerate(batted):
        out = b.dismissal is not None
        lines.append(BatterLine(
            player=b.name, runs=b.runs, balls=b.balls, fours=b.fours, sixes=b.sixes,
            strike_rate=round(b.runs / b.balls * 100, 2) if b.balls else None,
            on_strike=not st.finished and not out and i == st.striker, dismissal=b.dismissal or "not out"))
    bowling = [BowlerLine(player=b.name, overs=_overs(b.balls), maidens=b.maidens, runs=b.runs, wickets=b.wickets,
                          economy=round(b.runs / b.balls * 6, 2) if b.balls else None)
               for b in st.bowlers.values() if b.balls or b.runs]
    return InningsScore(
        number=number, team=team, runs=st.runs, wickets=st.wickets, overs=_overs(st.legal), legal_balls=st.legal,
        completed=st.finished, batting=lines, bowling=bowling, fall_of_wickets=st.fow,
        did_not_bat=[b.name for b in st.batters[st.next_idx:]] if st.finished else [])


@dataclass
class _Plan:
    batting: str
    bowling: str
    max_balls: int
    seed: int


@dataclass
class MatchDef:
    match_id: str
    format: str
    venue: str
    teams: tuple[str, str]
    innings: list[_Plan]
    start_innings: int
    start_balls: int

    @property
    def limited(self) -> bool:
        return self.format != "TEST"


DEFS = [
    MatchDef("mock-ind-aus-odi", "ODI", "Wankhede Stadium, Mumbai", ("India", "Australia"),
             [_Plan("India", "Australia", 300, 1), _Plan("Australia", "India", 300, 12)], 0, 150),
    MatchDef("mock-eng-pak-t20", "T20", "Lord's, London", ("England", "Pakistan"),
             [_Plan("Pakistan", "England", 120, 1), _Plan("England", "Pakistan", 120, 100)], 1, 6),
    MatchDef("mock-ind-aus-test", "TEST", "Melbourne Cricket Ground", ("India", "Australia"),
             [_Plan("Australia", "India", 99999, 1), _Plan("India", "Australia", 99999, 100),
              _Plan("Australia", "India", 99999, 33), _Plan("India", "Australia", 99999, 34)], 1, 180),
]


def play(defn: MatchDef, extra_balls: int, now: datetime) -> LiveMatch:
    scores: list[InningsScore] = []
    states: list[_State] = []
    budget = None
    for i, plan in enumerate(defn.innings):
        if i < defn.start_innings:
            limit = plan.max_balls
        elif budget is None:
            limit = defn.start_balls + extra_balls
        else:
            limit = budget
        target = states[0].runs + 1 if (defn.limited and i == 1) else None
        st = _simulate(SQUADS[plan.batting], SQUADS[plan.bowling], defn.format, plan.seed, plan.max_balls, limit, target)
        states.append(st)
        scores.append(_innings_score(i + 1, plan.batting, st, SQUADS[plan.batting]))
        if i >= defn.start_innings:
            budget = limit - st.legal
        if not st.finished:
            break

    last, st, plan = scores[-1], states[-1], defn.innings[len(scores) - 1]
    completed = st.finished and len(scores) == len(defn.innings)
    crr = round(st.runs / st.legal * BALLS_PER_OVER, 2) if st.legal else None
    live = not completed
    target = states[0].runs + 1 if (defn.limited and len(scores) == 2) else None
    need = target - st.runs if target else None
    rem = plan.max_balls - st.legal if target else None
    rrr = round(need / rem * BALLS_PER_OVER, 2) if live and target and rem and need and need > 0 else None

    if completed and defn.limited:
        if st.runs >= (target or 0):
            text = f"{plan.batting} won by {10 - st.wickets} wickets ({rem} balls remaining)"
        elif st.runs == target - 1:
            text = "Match tied"
        else:
            text = f"{defn.innings[0].batting} won by {target - 1 - st.runs} runs"
    elif completed:
        text = "Match drawn"
    elif target:
        text = f"{plan.batting} need {need} runs from {rem} balls"
    elif defn.format == "TEST":
        day = 1 + sum(s.legal for s in states) // TEST_BALLS_PER_DAY
        lead = ""
        if len(scores) > 1:
            diff = sum(s.runs for s, p in zip(states, defn.innings) if p.batting == plan.batting) - \
                sum(s.runs for s, p in zip(states, defn.innings) if p.batting != plan.batting)
            lead = f", {'lead' if diff > 0 else 'trail'} by {abs(diff)}"
        text = f"Day {day}: {plan.batting} batting{lead}"
    else:
        text = f"{plan.batting} batting"

    recent = [OverSummary(over=i + 1, balls=o, runs=sum(_token_runs(t) for t in o)) for i, o in enumerate(st.overs)][-3:]
    partnership = None
    if live:
        batters = [st.batters[st.striker].name, st.batters[st.non_striker].name]
        partnership = Partnership(runs=st.partnership_runs, balls=st.partnership_balls, batters=batters)
    return LiveMatch(
        match_id=defn.match_id, title=f"{defn.teams[0]} vs {defn.teams[1]} ({defn.format})", format=defn.format,
        status="COMPLETED" if completed else "LIVE", status_text=text, teams=list(defn.teams), venue=defn.venue,
        current_innings=last.number, innings=scores, current_run_rate=crr, required_run_rate=rrr, target=target,
        runs_required=max(need, 0) if need is not None else None, balls_remaining=rem if live and target else None,
        partnership=partnership, recent_overs=recent, updated_at=now)


class MockLiveProvider:
    name = "mock"
    is_mock = True

    def __init__(self, seconds_per_ball: float = 10.0, clock: Callable[[], float] = time.time) -> None:
        self.seconds_per_ball, self.clock, self.started = seconds_per_ball, clock, clock()
        self.fail = False

    def reset(self) -> None:
        self.started = self.clock()

    def _play(self, defn: MatchDef) -> LiveMatch:
        extra = int((self.clock() - self.started) // self.seconds_per_ball)
        return play(defn, extra, datetime.now(timezone.utc))

    def list_live_matches(self) -> list[MatchSummary]:
        if self.fail:
            raise ProviderError("mock provider unavailable")
        out = []
        for d in DEFS:
            m = self._play(d)
            if m.status == "LIVE":
                out.append(MatchSummary(match_id=m.match_id, title=m.title, format=m.format, status=m.status))
        return out

    def get_scorecard(self, match_id: str) -> LiveMatch:
        if self.fail:
            raise ProviderError("mock provider unavailable")
        for d in DEFS:
            if d.match_id == match_id:
                return self._play(d)
        raise ProviderError(f"unknown match {match_id}")
