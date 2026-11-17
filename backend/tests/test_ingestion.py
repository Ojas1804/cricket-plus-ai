from sqlalchemy import func, select

from app.cricket.ingestion.cricsheet import ingest_path
from app.cricket.models import BattingPerformance, BowlingPerformance, Innings, Match, Player, SourceMapping


def _player(session, name):
    return session.scalar(select(Player).where(Player.full_name == name))


def test_ingest_counts_and_rejections(session, match_dir):
    log = ingest_path(session, match_dir)
    assert (log.records_processed, log.records_rejected) == (1, 1)
    assert log.status == "COMPLETED_WITH_ERRORS" and "bad" in log.error_details
    assert session.scalar(select(func.count()).select_from(Match)) == 1
    assert session.scalar(select(func.count()).select_from(SourceMapping)) == 4


def test_ingestion_is_idempotent(session, match_dir):
    ingest_path(session, match_dir)
    log = ingest_path(session, match_dir)
    assert log.records_processed == 0
    assert session.scalar(select(func.count()).select_from(Match)) == 1


def test_super_over_skipped_and_innings_totals(session, match_dir):
    ingest_path(session, match_dir)
    innings = session.scalars(select(Innings)).all()
    assert len(innings) == 1
    assert (innings[0].runs, innings[0].wickets, innings[0].legal_balls) == (16, 2, 11)


def test_batting_performance(session, match_dir):
    ingest_path(session, match_dir)
    p1 = session.scalar(select(BattingPerformance).where(BattingPerformance.player_id == _player(session, "P1").id))
    assert (p1.runs, p1.balls_faced, p1.fours, p1.sixes, p1.is_dismissed) == (5, 4, 1, 0, True)
    p2 = session.scalar(select(BattingPerformance).where(BattingPerformance.player_id == _player(session, "P2").id))
    assert (p2.runs, p2.balls_faced, p2.sixes, p2.is_dismissed, p2.dismissal_type) == (8, 8, 1, True, "run out")


def test_bowling_performance(session, match_dir):
    ingest_path(session, match_dir)
    z = session.scalar(select(BowlingPerformance).where(BowlingPerformance.player_id == _player(session, "Z").id))
    assert (z.balls_bowled, z.runs_conceded, z.wickets, z.maidens, z.wides, z.no_balls) == (5, 15, 1, 0, 1, 1)
    y = session.scalar(select(BowlingPerformance).where(BowlingPerformance.player_id == _player(session, "Y").id))
    assert (y.balls_bowled, y.runs_conceded, y.wickets, y.maidens) == (6, 0, 0, 1)
