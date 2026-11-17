"""Cricsheet JSON ingestion. Run as a separate command: python -m app.cricket.ingestion.cricsheet <dir|zip>."""
import json
import sys
import zipfile
from collections import defaultdict
from collections.abc import Iterator
from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics.metrics import cricket_metrics as m
from app.cricket.normalization.geography import infer_venue_country, team_country
from app.cricket.models import (
    BattingPerformance, BowlingPerformance, Competition, DataIngestionLog, Delivery, Innings,
    Match, Player, SourceMapping, Team, Venue,
)

PROVIDER = "cricsheet"
FORMATS = {"Test": "TEST", "ODI": "ODI", "IT20": "T20I", "T20": "T20", "ODM": "LIST_A", "MDM": "FIRST_CLASS"}


class RejectedMatch(Exception):
    pass


class _Resolver:
    """Get-or-create canonical entities, caching lookups for the duration of a run."""

    def __init__(self, session: Session) -> None:
        self.s = session
        self.players: dict[str, int] = {}
        self.teams: dict[str, int] = {}
        self.venues: dict[tuple, int] = {}
        self.comps: dict[tuple, int] = {}

    def player(self, name: str, registry: dict) -> int:
        provider_id = registry.get(name) or f"name:{name}"
        if provider_id in self.players:
            return self.players[provider_id]
        mapping = self.s.scalar(select(SourceMapping).where(
            SourceMapping.entity_type == "player", SourceMapping.provider == PROVIDER,
            SourceMapping.provider_id == provider_id))
        if mapping:
            pid = mapping.canonical_id
        else:
            player = Player(full_name=name, display_name=name, aliases=[])
            self.s.add(player)
            self.s.flush()
            self.s.add(SourceMapping(entity_type="player", canonical_id=player.id, provider=PROVIDER, provider_id=provider_id))
            pid = player.id
        self.players[provider_id] = pid
        return pid

    def team(self, name: str, team_type: str) -> int:
        if name not in self.teams:
            team = self.s.scalar(select(Team).where(Team.name == name))
            if not team:
                team = Team(name=name, team_type=team_type, country=team_country(name, team_type))
                self.s.add(team)
                self.s.flush()
            self.teams[name] = team.id
        return self.teams[name]

    def venue(self, name: str | None, city: str | None) -> int | None:
        if not name:
            return None
        key = (name, city)
        if key not in self.venues:
            venue = self.s.scalar(select(Venue).where(Venue.name == name, Venue.city == city))
            if not venue:
                venue = Venue(name=name, city=city, country=infer_venue_country(city, name))
                self.s.add(venue)
                self.s.flush()
            self.venues[key] = venue.id
        return self.venues[key]

    def competition(self, name: str, fmt: str, comp_type: str) -> int:
        key = (name, fmt)
        if key not in self.comps:
            comp = self.s.scalar(select(Competition).where(Competition.name == name, Competition.format == fmt))
            if not comp:
                comp = Competition(name=name, format=fmt, competition_type=comp_type)
                self.s.add(comp)
                self.s.flush()
            self.comps[key] = comp.id
        return self.comps[key]


def ingest_match(session: Session, data: dict, source_id: str, resolver: _Resolver | None = None) -> bool:
    """Returns False if the match already exists. Raises RejectedMatch for invalid input."""
    if session.scalar(select(Match.id).where(Match.source_id == source_id)):
        return False
    r = resolver or _Resolver(session)
    info = data.get("info") or {}
    teams, dates = info.get("teams") or [], info.get("dates") or []
    if len(teams) != 2 or not dates or info.get("match_type") not in FORMATS or not data.get("innings"):
        raise RejectedMatch("missing teams, dates, known match_type or innings")

    fmt = FORMATS[info["match_type"]]
    team_type = info.get("team_type", "unknown")
    registry = (info.get("registry") or {}).get("people", {})
    event = (info.get("event") or {}).get("name")
    comp_id = r.competition(event or f"{team_type.title()} {fmt}", fmt, "league" if event and team_type == "club" else team_type)
    team_ids = {t: r.team(t, team_type) for t in teams}
    winner = (info.get("outcome") or {}).get("winner")

    match = Match(
        source_id=source_id, competition_id=comp_id, season=str(info["season"]) if info.get("season") else None,
        format=fmt, team_1_id=team_ids[teams[0]], team_2_id=team_ids[teams[1]],
        venue_id=r.venue(info.get("venue"), info.get("city")), start_time=date.fromisoformat(dates[0]),
        status="COMPLETED", winner_id=team_ids.get(winner),
    )
    session.add(match)
    session.flush()

    number = 0
    for inn in data["innings"]:
        if inn.get("super_over"):
            continue
        number += 1
        batting_team = inn["team"]
        if batting_team not in team_ids:
            raise RejectedMatch(f"innings team {batting_team} not in match teams")
        bowling_team = teams[1] if batting_team == teams[0] else teams[0]
        _ingest_innings(session, r, match, number, inn, team_ids[batting_team], team_ids[bowling_team], registry)
    session.flush()
    return True


def _ingest_innings(session, r, match, number, inn, batting_team_id, bowling_team_id, registry) -> None:
    innings = Innings(match_id=match.id, innings_number=number, batting_team_id=batting_team_id, bowling_team_id=bowling_team_id)
    session.add(innings)
    session.flush()

    bat: dict[int, dict] = defaultdict(lambda: {"runs": 0, "balls": 0, "fours": 0, "sixes": 0, "dismissal": None, "out": False})
    bowl: dict[int, dict] = defaultdict(lambda: {"balls": 0, "runs": 0, "wkts": 0, "maidens": 0, "wides": 0, "noballs": 0})
    deliveries, total_runs, wickets, legal_balls = [], 0, 0, 0

    for over in inn.get("overs", []):
        over_charge: dict[int, list[int]] = defaultdict(lambda: [0, 0])  # bowler -> [runs charged, legal balls]
        for idx, d in enumerate(over.get("deliveries", []), start=1):
            batter, bowler = r.player(d["batter"], registry), r.player(d["bowler"], registry)
            runs, extras = d["runs"], d.get("extras")
            legal = m.is_legal_delivery(extras)
            charged = m.runs_charged_to_bowler(runs["total"], extras)
            wkts = d.get("wickets", [])

            b = bat[batter]
            b["runs"] += runs["batter"]
            b["balls"] += m.batter_faced_ball(extras)
            if runs["batter"] in (4, 6) and not runs.get("non_boundary"):
                b["fours" if runs["batter"] == 4 else "sixes"] += 1

            bw = bowl[bowler]
            bw["runs"] += charged
            bw["balls"] += legal
            bw["wides"] += bool(extras and "wides" in extras)
            bw["noballs"] += bool(extras and "noballs" in extras)
            over_charge[bowler][0] += charged
            over_charge[bowler][1] += legal

            first_out = None
            for w in wkts:
                out_id = r.player(w["player_out"], registry)
                pb = bat[out_id]
                pb["dismissal"], pb["out"] = w["kind"], m.is_batting_dismissal(w["kind"])
                if m.is_bowler_wicket(w["kind"]):
                    bw["wkts"] += 1
                if m.is_batting_dismissal(w["kind"]):
                    wickets += 1
                first_out = first_out or (w["kind"], out_id)

            total_runs += runs["total"]
            legal_balls += legal
            deliveries.append(Delivery(
                innings_id=innings.id, over_number=over["over"], ball_number=idx, batter_id=batter, bowler_id=bowler,
                runs_batter=runs["batter"], runs_extras=runs["extras"], runs_total=runs["total"],
                wicket_type=first_out[0] if first_out else None, dismissed_player_id=first_out[1] if first_out else None,
                is_legal_delivery=legal, extra_type=",".join(extras) if extras else None))
        for bowler, (charged, legal_n) in over_charge.items():
            if legal_n == m.BALLS_PER_OVER and charged == 0:
                bowl[bowler]["maidens"] += 1

    innings.runs, innings.wickets, innings.legal_balls = total_runs, wickets, legal_balls
    session.add_all(deliveries)
    session.add_all(BattingPerformance(
        match_id=match.id, player_id=pid, innings_id=innings.id, runs=v["runs"], balls_faced=v["balls"],
        fours=v["fours"], sixes=v["sixes"], dismissal_type=v["dismissal"], is_dismissed=v["out"]) for pid, v in bat.items())
    session.add_all(BowlingPerformance(
        match_id=match.id, player_id=pid, innings_id=innings.id, balls_bowled=v["balls"], runs_conceded=v["runs"],
        wickets=v["wkts"], maidens=v["maidens"], wides=v["wides"], no_balls=v["noballs"]) for pid, v in bowl.items())


def _iter_files(path: Path) -> Iterator[tuple[str, dict]]:
    if path.suffix == ".zip":
        with zipfile.ZipFile(path) as z:
            for name in sorted(z.namelist()):
                if name.endswith(".json"):
                    yield Path(name).stem, json.loads(z.read(name))
    else:
        for f in sorted(path.glob("*.json")):
            yield f.stem, json.loads(f.read_text(encoding="utf-8"))


def ingest_path(session: Session, path: Path) -> DataIngestionLog:
    resolver = _Resolver(session)
    processed = rejected = 0
    errors: list[str] = []
    for source_id, data in _iter_files(path):
        try:
            if ingest_match(session, data, source_id, resolver):
                processed += 1
            session.commit()
        except (RejectedMatch, KeyError, ValueError, TypeError) as e:
            session.rollback()
            resolver = _Resolver(session)
            rejected += 1
            errors.append(f"{source_id}: {type(e).__name__}: {e}")
    log = DataIngestionLog(
        source=PROVIDER, dataset=path.name, ingested_at=datetime.now(timezone.utc), records_processed=processed,
        records_rejected=rejected, status="COMPLETED" if not rejected else "COMPLETED_WITH_ERRORS",
        error_details="\n".join(errors[:50]) or None)
    session.add(log)
    session.commit()
    return log


def main(argv: list[str]) -> int:
    from app.database.session import get_engine

    if len(argv) != 1:
        print("usage: python -m app.cricket.ingestion.cricsheet <directory|zip>")
        return 2
    with Session(get_engine()) as session:
        log = ingest_path(session, Path(argv[0]))
    print(f"processed={log.records_processed} rejected={log.records_rejected} status={log.status}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
