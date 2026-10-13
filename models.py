from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    nickname_cs2: Mapped[str | None] = mapped_column(String(128), nullable=True)
    steam_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    role: Mapped[str] = mapped_column(String(16), default="user", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    teams = relationship("TeamMember", back_populates="user", cascade="all, delete-orphan")
    registrations = relationship("TournamentRegistration", back_populates="user")


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    tag: Mapped[str | None] = mapped_column(String(16), nullable=True)
    captain_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    player_profile_links: Mapped[list[str]] = mapped_column(JSON, default=list)
    is_singleton: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    captain = relationship("User", foreign_keys=[captain_id])
    members = relationship("TeamMember", back_populates="team", cascade="all, delete-orphan")
    registrations = relationship(
        "TournamentRegistration",
        back_populates="team",
        foreign_keys="TournamentRegistration.team_id",
    )


class TeamMember(Base):
    __tablename__ = "team_members"

    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    team = relationship("Team", back_populates="members")
    user = relationship("User", back_populates="teams")


class Tournament(Base):
    __tablename__ = "tournaments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    game_format: Mapped[str] = mapped_column(String(8))
    bracket_type: Mapped[str] = mapped_column(String(24), default="single_elimination")
    status: Mapped[str] = mapped_column(String(16), default="registration", index=True)
    start_date: Mapped[datetime] = mapped_column(DateTime)
    registration_deadline: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    max_teams: Mapped[int] = mapped_column(Integer)
    prize_pool: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rules: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    registrations = relationship(
        "TournamentRegistration", back_populates="tournament", cascade="all, delete-orphan"
    )
    matches = relationship("Match", back_populates="tournament", cascade="all, delete-orphan")


class TournamentRegistration(Base):
    __tablename__ = "tournament_registrations"
    __table_args__ = (
        CheckConstraint(
            "(team_id IS NOT NULL AND user_id IS NULL) OR (team_id IS NULL AND user_id IS NOT NULL)",
            name="registration_subject_check",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tournament_id: Mapped[int] = mapped_column(ForeignKey("tournaments.id", ondelete="CASCADE"), index=True)
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id", ondelete="RESTRICT"), nullable=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    participant_team_id: Mapped[int | None] = mapped_column(
        ForeignKey("teams.id", ondelete="SET NULL"), nullable=True
    )
    registration_type: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), default="confirmed", index=True)
    registered_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    tournament = relationship("Tournament", back_populates="registrations")
    team = relationship("Team", foreign_keys=[team_id], back_populates="registrations")
    user = relationship("User", back_populates="registrations")
    participant_team = relationship("Team", foreign_keys=[participant_team_id])


class Match(Base):
    __tablename__ = "matches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tournament_id: Mapped[int] = mapped_column(ForeignKey("tournaments.id", ondelete="CASCADE"), index=True)
    bracket: Mapped[str] = mapped_column(String(16), default="single")
    stage: Mapped[str] = mapped_column(String(64))
    round_number: Mapped[int] = mapped_column(Integer, default=1)
    bracket_position: Mapped[int] = mapped_column(Integer, default=0)
    team1_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"), nullable=True)
    team2_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"), nullable=True)
    score1: Mapped[int | None] = mapped_column(Integer, nullable=True)
    score2: Mapped[int | None] = mapped_column(Integer, nullable=True)
    winner_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="waiting", index=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    next_match_id: Mapped[int | None] = mapped_column(ForeignKey("matches.id"), nullable=True)
    next_slot: Mapped[int | None] = mapped_column(Integer, nullable=True)
    loser_next_match_id: Mapped[int | None] = mapped_column(ForeignKey("matches.id"), nullable=True)
    loser_next_slot: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    tournament = relationship("Tournament", back_populates="matches")
    team1 = relationship("Team", foreign_keys=[team1_id])
    team2 = relationship("Team", foreign_keys=[team2_id])
    winner = relationship("Team", foreign_keys=[winner_id])
