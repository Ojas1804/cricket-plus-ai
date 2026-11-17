from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class Player(Base):
    __tablename__ = "players"
    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(200), index=True)
    display_name: Mapped[str] = mapped_column(String(200))
    country: Mapped[str | None] = mapped_column(String(100))
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    role: Mapped[str | None] = mapped_column(String(50))
    batting_style: Mapped[str | None] = mapped_column(String(50))
    bowling_style: Mapped[str | None] = mapped_column(String(50))
    aliases: Mapped[list] = mapped_column(JSON, default=list)


class Team(Base):
    __tablename__ = "teams"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    country: Mapped[str | None] = mapped_column(String(100))
    team_type: Mapped[str] = mapped_column(String(30), default="unknown")


class Venue(Base):
    __tablename__ = "venues"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    city: Mapped[str | None] = mapped_column(String(100))
    country: Mapped[str | None] = mapped_column(String(100), index=True)
    timezone: Mapped[str | None] = mapped_column(String(50))
    __table_args__ = (UniqueConstraint("name", "city"),)


class Competition(Base):
    __tablename__ = "competitions"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    competition_type: Mapped[str] = mapped_column(String(30), default="unknown")
    format: Mapped[str] = mapped_column(String(20))
    __table_args__ = (UniqueConstraint("name", "format"),)


class Match(Base):
    __tablename__ = "matches"
    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[str] = mapped_column(String(100), unique=True)
    competition_id: Mapped[int | None] = mapped_column(ForeignKey("competitions.id"), index=True)
    season: Mapped[str | None] = mapped_column(String(20), index=True)
    format: Mapped[str] = mapped_column(String(20), index=True)
    team_1_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    team_2_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    venue_id: Mapped[int | None] = mapped_column(ForeignKey("venues.id"), index=True)
    start_time: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(20), default="COMPLETED")
    winner_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"))


class Innings(Base):
    __tablename__ = "innings"
    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    innings_number: Mapped[int] = mapped_column(Integer)
    batting_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    bowling_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    runs: Mapped[int] = mapped_column(Integer, default=0)
    wickets: Mapped[int] = mapped_column(Integer, default=0)
    legal_balls: Mapped[int] = mapped_column(Integer, default=0)
    __table_args__ = (Index("ix_innings_match_batting", "match_id", "batting_team_id"),
                      Index("ix_innings_match_bowling", "match_id", "bowling_team_id"))


class Delivery(Base):
    __tablename__ = "deliveries"
    id: Mapped[int] = mapped_column(primary_key=True)
    innings_id: Mapped[int] = mapped_column(ForeignKey("innings.id"), index=True)
    over_number: Mapped[int] = mapped_column(Integer)
    ball_number: Mapped[int] = mapped_column(Integer)
    batter_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)
    bowler_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)
    runs_batter: Mapped[int] = mapped_column(Integer)
    runs_extras: Mapped[int] = mapped_column(Integer)
    runs_total: Mapped[int] = mapped_column(Integer)
    wicket_type: Mapped[str | None] = mapped_column(String(40))
    dismissed_player_id: Mapped[int | None] = mapped_column(ForeignKey("players.id"))
    is_legal_delivery: Mapped[bool] = mapped_column(Boolean)
    extra_type: Mapped[str | None] = mapped_column(String(40))


class BattingPerformance(Base):
    __tablename__ = "batting_performances"
    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)
    innings_id: Mapped[int] = mapped_column(ForeignKey("innings.id"), index=True)
    runs: Mapped[int] = mapped_column(Integer, default=0)
    balls_faced: Mapped[int] = mapped_column(Integer, default=0)
    fours: Mapped[int] = mapped_column(Integer, default=0)
    sixes: Mapped[int] = mapped_column(Integer, default=0)
    dismissal_type: Mapped[str | None] = mapped_column(String(40))
    is_dismissed: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (UniqueConstraint("innings_id", "player_id"),)


class BowlingPerformance(Base):
    __tablename__ = "bowling_performances"
    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)
    innings_id: Mapped[int] = mapped_column(ForeignKey("innings.id"), index=True)
    balls_bowled: Mapped[int] = mapped_column(Integer, default=0)
    runs_conceded: Mapped[int] = mapped_column(Integer, default=0)
    wickets: Mapped[int] = mapped_column(Integer, default=0)
    maidens: Mapped[int] = mapped_column(Integer, default=0)
    wides: Mapped[int] = mapped_column(Integer, default=0)
    no_balls: Mapped[int] = mapped_column(Integer, default=0)
    __table_args__ = (UniqueConstraint("innings_id", "player_id"),)


class SourceMapping(Base):
    __tablename__ = "source_mappings"
    id: Mapped[int] = mapped_column(primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(30))
    canonical_id: Mapped[int] = mapped_column(Integer)
    provider: Mapped[str] = mapped_column(String(50))
    provider_id: Mapped[str] = mapped_column(String(100))
    __table_args__ = (
        UniqueConstraint("entity_type", "provider", "provider_id"),
        Index("ix_source_mappings_canonical", "entity_type", "canonical_id"),
    )


class DataIngestionLog(Base):
    __tablename__ = "data_ingestion_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(50))
    dataset: Mapped[str] = mapped_column(String(200))
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    records_processed: Mapped[int] = mapped_column(Integer, default=0)
    records_rejected: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20))
    error_details: Mapped[str | None] = mapped_column(Text)
