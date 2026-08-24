from datetime import datetime
from typing import List, Optional
from sqlalchemy import String, Integer, DateTime, Numeric, Boolean, ForeignKey, Index
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase):
    pass

class League(Base):
    __tablename__ = "leagues"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[int] = mapped_column(unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    category: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    teams: Mapped[List["Team"]] = relationship(back_populates="league")

class Team(Base):
    __tablename__ = "teams"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[Optional[int]] = mapped_column(index=True)
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id"))
    source_name: Mapped[str] = mapped_column(String(255))
    canonical_name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    league: Mapped["League"] = relationship(back_populates="teams")

class Match(Base):
    __tablename__ = "matches"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[Optional[int]] = mapped_column(index=True)
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id"), index=True)
    home_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    away_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    status: Mapped[str] = mapped_column(String(50), default="UPCOMING", index=True)  # UPCOMING, COMPLETED, AMBIGUOUS
    
    home_score: Mapped[Optional[int]] = mapped_column(Integer)
    away_score: Mapped[Optional[int]] = mapped_column(Integer)
    half_home_score: Mapped[Optional[int]] = mapped_column(Integer)
    half_away_score: Mapped[Optional[int]] = mapped_column(Integer)
    
    result: Mapped[Optional[str]] = mapped_column(String(10)) # HOME, DRAW, AWAY
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    odds_snapshots: Mapped[List["OddsSnapshot"]] = relationship(back_populates="match")
    events: Mapped[List["MatchEvent"]] = relationship(back_populates="match")

class OddsSnapshot(Base):
    __tablename__ = "odds_snapshots"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)
    
    home_odds: Mapped[float] = mapped_column(Numeric(10, 3))
    draw_odds: Mapped[float] = mapped_column(Numeric(10, 3))
    away_odds: Mapped[float] = mapped_column(Numeric(10, 3))
    
    raw_hash: Mapped[Optional[str]] = mapped_column(String(255))
    
    match: Mapped["Match"] = relationship(back_populates="odds_snapshots")

class MatchEvent(Base):
    __tablename__ = "match_events"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(50)) # e.g. GOAL
    team_id: Mapped[Optional[int]] = mapped_column(ForeignKey("teams.id"))
    team_name: Mapped[Optional[str]] = mapped_column(String(255))
    minute: Mapped[int] = mapped_column(Integer)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    
    match: Mapped["Match"] = relationship(back_populates="events")

class RankingSnapshot(Base):
    __tablename__ = "ranking_snapshots"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id"), index=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)
    source_hash: Mapped[str] = mapped_column(String(255))

    entries: Mapped[List["RankingEntry"]] = relationship(back_populates="snapshot")

class RankingEntry(Base):
    __tablename__ = "ranking_entries"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("ranking_snapshots.id"), index=True)
    team_id: Mapped[Optional[int]] = mapped_column(ForeignKey("teams.id"), index=True)
    team_name: Mapped[Optional[str]] = mapped_column(String(255))
    rank: Mapped[int] = mapped_column(Integer)
    points: Mapped[int] = mapped_column(Integer)
    
    form_position_1: Mapped[Optional[str]] = mapped_column(String(10))
    form_position_2: Mapped[Optional[str]] = mapped_column(String(10))
    form_position_3: Mapped[Optional[str]] = mapped_column(String(10))
    form_position_4: Mapped[Optional[str]] = mapped_column(String(10))
    form_position_5: Mapped[Optional[str]] = mapped_column(String(10))
    
    snapshot: Mapped["RankingSnapshot"] = relationship(back_populates="entries")

class RawPayload(Base):
    __tablename__ = "raw_payloads"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    source_type: Mapped[str] = mapped_column(String(50)) # matches, results, ranking
    endpoint: Mapped[str] = mapped_column(String(1024))
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    payload_hash: Mapped[str] = mapped_column(String(255), index=True)
    storage_path: Mapped[str] = mapped_column(String(1024))
    http_status: Mapped[int] = mapped_column(Integer)
